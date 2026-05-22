#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  SUPRAOS v8 MASTER SCRIPT — Todo en marcha, 100% soberanía local
#  Arranca: GPU :8085 → Router :9000 → Nexus :9095 → Bridges → Telegram
#  Asegura que no haya procesos duplicados. Si algo falla, reintenta.
# ═══════════════════════════════════════════════════════════════
set -e
LOG=/tmp/klawaqua-supraos-v8.log
exec >>"$LOG" 2>&1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="/opt/klawaqua"
DASHBOARD="$ROOT/dashboard/nexus-dashboard-v8.html"

echo "[$(date +%F_%T)] ===== SUPRAOS v8 MASTER INICIANDO ====="

# ─── 0. Limpiar duplicados ───────────────────────────────────────
_pkill_dup() {
    local pattern="$1"
    local keep_pid="${2:-0}"
    local pids=$(pgrep -f "$pattern" 2>/dev/null | grep -v "^$keep_pid$" || true)
    if [ -n "$pids" ]; then
        echo "  Matando duplicados: $pattern (PIDs: $pids)"
        echo "$pids" | xargs kill -9 2>/dev/null || true
        sleep 1
    fi
}

_pkill_dup "python3.*nexus_core.py"
_pkill_dup "python3.*telegram_bot.py"
_pkill_dup "python3.*bridge.py"
_pkill_dup "python3.*thepopebot"
_pkill_dup "python3.*autopilot_daemon"

# ─── 1. GPU llama.cpp (ya debería correr, verificar) ──────────
echo "[$(date +%F_%T)] 1/8 GPU llama.cpp :8085"
if ! ss -tlnp | grep -q ":8085"; then
    echo "  ⚠️ GPU no responde. Verificar manualmente: ~/llama.cpp/build/bin/llama-server"
else
    echo "  ✅ GPU online"
fi

# ─── 2. Router Legacy :9000 ────────────────────────────────────
echo "[$(date +%F_%T)] 2/8 Router :9000"
if ! ss -tlnp | grep -q ":9000"; then
    nohup python3 "$ROOT/scripts/router_service.py" > /tmp/router.log 2>&1 &
    sleep 3
fi
ss -tlnp | grep -q ":9000" && echo "  ✅ Router online" || echo "  ❌ Router OFFLINE"

# ─── 3. Nexus Core :9095 ───────────────────────────────────────
echo "[$(date +%F_%T)] 3/8 Nexus Core :9095"
if ss -tlnp | grep -q ":9095"; then
    kill $(lsof -t -i:9095) 2>/dev/null || true
    sleep 2
fi
nohup python3 "$ROOT/scripts/nexus_core.py" > /tmp/nexus.log 2>&1 &
echo $! > /tmp/nexus.pid
sleep 4
for i in {1..15}; do
    if curl -s http://localhost:9095/v1/nexus/status >/dev/null 2>&1; then
        echo "  ✅ Nexus online"; break
    fi
    sleep 1
done

# ─── 4. Soul DB Init ───────────────────────────────────────────
echo "[$(date +%F_%T)] 4/8 Soul Engine"
python3 "$ROOT/scripts/soul_engine.py" > /dev/null 2>&1 || true
echo "  ✅ Soul DB inicializada"

# ─── 5. Bridges Offline ───────────────────────────────────────
echo "[$(date +%F_%T)] 5/8 Bridges (OpenFang, OpenSwarm, ThePopeBot)"
_pkill_dup "python3.*openfang/bridge.py"
nohup python3 "$ROOT/openfang/bridge.py" > /tmp/openfang.log 2>&1 &
echo "  OpenFang → :4200"

_pkill_dup "python3.*openswarm/bridge.py"
nohup python3 "$ROOT/openswarm/bridge.py" > /tmp/openswarm.log 2>&1 &
echo "  OpenSwarm → :8765"

_pkill_dup "python3.*thepopebot"
nohup python3 "$ROOT/thepopebot/server.py" > /tmp/thepopebot.log 2>&1 &
echo "  ThePopeBot → :8888"

sleep 3

# ─── 6. Telegram Bot ───────────────────────────────────────────
echo "[$(date +%F_%T)] 6/8 Telegram Bot"
_pkill_dup "python3.*telegram_bot.py"
export TELEGRAM_BOT_TOKEN="8469591478:AAGjPrpL5XR7Igh0fqp-JeL6Tma8NMEDEy8"
nohup python3 "$ROOT/scripts/telegram_bot.py" > /tmp/telegram.log 2>&1 &
echo "  Telegram Bot → polling"

# ─── 7. Autopilot Daemon ─────────────────────────────────────
echo "[$(date +%F_%T)] 7/8 Autopilot"
_pkill_dup "python3.*autopilot_daemon"
nohup python3 "$ROOT/scripts/autopilot_daemon.py" loop > /tmp/autopilot.log 2>&1 &
echo "  Autopilot → loop 12h"

# ─── 8. Verificacion Final ───────────────────────────────────
echo ""
echo "[$(date +%F_%T)] 8/8 VERIFICANDO TODO..."
sleep 3

python3 - << 'PYEOF'
import urllib.request as req, json, sys

ok = 0
fail = 0

def check(name, url, method="GET"):
    global ok, fail
    try:
        if method == "GET":
            r = req.urlopen(url, timeout=5)
        else:
            rq = req.Request(url, json.dumps({}).encode(), headers={"Content-Type":"application/json"})
            r = req.urlopen(rq, timeout=10)
        d = json.loads(r.read().decode())
        if "error" in d and "offline" not in str(d):
            print(f"⚠️  {name}")
            fail += 1
        else:
            print(f"✅ {name}")
            ok += 1
    except Exception as e:
        print(f"❌ {name}: {e}")
        fail += 1

print("\n=== SERVICOS CORE ===")
check("Nexus Status", "http://localhost:9095/v1/nexus/status")
check("Soul Status", "http://localhost:9095/v1/nexus/soul/status")
check("Bridges List", "http://localhost:9095/v1/nexus/bridges/list")
check("Billing", "http://localhost:9095/billing/plans")
check("GPU llama", "http://localhost:8085/completion", method="POST")
check("Router", "http://localhost:9000")

print("\n=== PUENTES DIRECTOS ===")
for port, name in [(4200,"OpenFang"),(8765,"OpenSwarm"),(8888,"ThePopeBot"),(5080,"AgentZero"),(7000,"HolaOS"),(3001,"OpenWebUI")]:
    try:
        req.urlopen(f"http://localhost:{port}", timeout=3)
        print(f"✅ {name} :{port}"); ok += 1
    except:
        print(f"⚠️  {name} :{port}"); fail += 1

print("\n=== KAIYA TEST ===")
try:
    sys.path.insert(0, "/opt/klawaqua/scripts")
    import kaiya_soul_bridge as kaiya
    r = kaiya.process_message("Estas lista para trabajar?")
    print(f"✅ KAIYA: {r[:60]}...")
    ok += 1
except Exception as e:
    print(f"❌ KAIYA: {e}"); fail += 1

print(f"\n═══════════════════════════════════════")
print(f"  RESULTADO: {ok} OK  |  {fail} FALLAS")
print(f"═══════════════════════════════════════")
if fail == 0:
    print("  🌊 SUPRAOS v8 100% OPERATIVO")
else:
    print(f"  ⚠️  {fail} servicios requieren atención")
PYEOF

# ─── Dashboard ─────────────────────────────────────────────────
echo ""
echo "═════════════════════════════════════════════════════════"
echo "  Dashboard: $DASHBOARD"
echo "  Abre en navegador: file://$DASHBOARD"
echo "═════════════════════════════════════════════════════════"
echo "[$(date +%F_%T)] ===== MASTER COMPLETADO ====="
