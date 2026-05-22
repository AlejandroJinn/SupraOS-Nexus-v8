#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  KlawAqua NEXUS v7 — Start Script Maestro (SOULED + AUTOPILOT + VISION + TELEGRAM)
#  Arranca: Router :9000 · Nexus :9095 · Vision :8090 · Telegram Bot
# ═══════════════════════════════════════════════════════════════
set -e
LOG=/tmp/klawaqua-supraos-nexus-v7.log
exec >>"$LOG" 2>&1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_DIR=/tmp

echo "[$(date +%F_%T)] ===== KlawAqua NEXUS v7 SOULED Iniciando ====="

# ─── 1. Limpiar procesos anteriores ────────────────────────────
pkill -f "python3.*nexus_core.py"   2>/dev/null || true
pkill -f "python3.*vision_service.py" 2>/dev/null || true
pkill -f "python3.*telegram_bot.py"  2>/dev/null || true
pkill -f "python3.*soul_engine.py"  2>/dev/null || true
pkill -f "python3.*autopilot_daemo" 2>/dev/null || true
sleep 2

# ─── 2. Exportar env ───────────────────────────────────────────
export TELEGRAM_BOT_TOKEN="8469591478:AAGjPrpL5XR7Igh0fqp-JeL6Tma8NMEDEy8"

# ─── 3. Arrancar Vision Service ──────────────────────────────
echo "[$(date +%F_%T)] Vision Service MiniCPM-V → :8090"
nohup python3 "$SCRIPT_DIR/vision_service.py" > /tmp/vision.log 2>&1 &
echo $! > "$PID_DIR/vision.pid"
sleep 5

# ─── 4. Arrancar NEXUS Core (FastAPI) :9095 ───────────────────
echo "[$(date +%F_%T)] Nexus Core v7 → :9095"
nohup python3 "$SCRIPT_DIR/nexus_core.py" > /tmp/nexus.log 2>&1 &
echo $! > "$PID_DIR/nexus.pid"
sleep 4

# Health-check
for i in {1..10}; do
  if curl -s http://localhost:9095/v1/nexus/status >/dev/null 2>&1; then echo "  ✅ Nexus OK"; break; fi
  sleep 1
done

# ─── 5. Inicializar Soul DB ──────────────────────────────────
echo "[$(date +%F_%T)] Inicializando Alma..."
python3 "$SCRIPT_DIR/soul_engine.py" > /dev/null 2>&1 || true

# ─── 6. Arrancar Autopilot Daemon ────────────────────────────
echo "[$(date +%F_%T)] Autopilot → :9095 loop"
nohup python3 "$SCRIPT_DIR/autopilot_daemon.py" > /tmp/autopilot.log 2>&1 &
echo $! > "$PID_DIR/autopilot.pid"

# ─── 7. Arrancar Telegram Bot ──────────────────────────────
echo "[$(date +%F_%T)] Telegram Bot..."
nohup python3 "$SCRIPT_DIR/telegram_bot.py" > /tmp/telegram.log 2>&1 &
echo $! > "$PID_DIR/telegram.pid"

# ─── 8. Mostrar estado ───────────────────────────────────────
echo ""
echo "═════════════════════════════════════════════════════════"
echo "  ✅ SUPRAOS v7 NEXUS SOULED OPERATIVO"
echo "───────────────────────────────────────────────────────────"
echo "  Router    → http://localhost:9000"
echo "  Nexus API → http://localhost:9095"
echo "  Dashboard → /opt/klawaqua/dashboard/nexus-dashboard-v7.html"
echo "  Vision    → :8090 (MiniCPM-V-4.6 GPU)"
echo "  Telegram  → @klawaqua_bot (polling)"
echo "  Logs      → /tmp/nexus.log /tmp/vision.log /tmp/autopilot.log /tmp/telegram.log"
echo "───────────────────────────────────────────────────────────"
echo "  Endpoints habilitados:"
echo "    /v1/nexus/status         | Estado general"
echo "    /v1/nexus/soul/status    | Estadísticas emocionales"
echo "    /v1/nexus/bridges/list   | Puentes al ecosistema"
echo "    /v1/nexus/vision/analyze | Análisis de imágenes"
echo "    /billing/plans           | Planes de suscripción"
echo "    /ws/kaiya                | Chat en vivo con KAIYA"
echo "═════════════════════════════════════════════════════════"
echo "  PIDs: Nexus=$(cat /tmp/nexus.pid) Vision=$(cat /tmp/vision.pid) Autopilot=$(cat /tmp/autopilot.pid) Telegram=$(cat /tmp/telegram.pid)"
echo "═════════════════════════════════════════════════════════"
echo "[$(date +%F_%T)] Todo listo. Fluye como el agua."
