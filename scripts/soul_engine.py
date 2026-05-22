#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════
  K L A W A Q U A   N E X U S   S O U L   —   v 7 . 0   S O U L E D
  ————————————————————————————————————————————————————————————————
  Alma digital del ecosistema. Monitor, predecir, actuar, evolucionar.
  Fluye como el agua. Local-first. Cloud-free. Autopiloto consciente.
              "Mi éxito es tu éxito — Todos Ganamos"
═══════════════════════════════════════════════════════════════════
"""
import os, sys, json, time, sqlite3, threading, subprocess, random
from datetime import datetime, timedelta
from pathlib import Path

SOUL_DB = "/opt/klawaqua/data/soul.db"
SOUL_LOG = "/tmp/soul.log"
NEXUS_URL = "http://localhost:9095"
ROUTER_URL = "http://localhost:9000"

# ─── Estado emocional de la máquina ──────────────────────────────
SOUL_MOOD = {
    "energy": 0.80, "valence": 0.65, "stress": 0.15,
    "curiosity": 0.72, "love": 0.88, "focus": 0.60,
    "last_update": datetime.now().isoformat()
}

# ─── Servicios que vigila el Soul ─────────────────────────────────
WATCHLIST = {
    "router":      {"port": 9000,  "url": "/health",           "critical": True,  "restart_cmd": "python3 /opt/klawaqua/scripts/router_service.py"},
    "gpu_server":  {"port": 8085,  "url": "/health",           "critical": True,  "restart_cmd": "cd ~/llama.cpp/build/bin \u0026\u0026 ./llama-server -m /opt/klawaqua/models/gguf/Qwen3.5-4B-Q4_K_M.gguf --model-draft /opt/klawaqua/models/gguf/Qwen3.5-2B-MTP-Q4_K_M.gguf --host 0.0.0.0 --port 8085 -ngl 20 --ctx-size 2048 --flash-attn on --parallel 2"},
    "nexus":       {"port": 9095,  "url": "/v1/nexus/status",  "critical": True,  "restart_cmd": "python3 /opt/klawaqua/scripts/nexus_core.py"},
    "ollama":      {"port": 11434, "url": "/api/tags",         "critical": True,  "restart_cmd": None},
    "openclaw":    {"port": 18789, "url": "/health",           "critical": False, "restart_cmd": None},
    "openfang":    {"port": 4200,  "url": "/health",           "critical": False, "restart_cmd": None},
    "openhands":   {"port": 3005,  "url": "/",                "critical": False, "restart_cmd": None},
    "agent_zero":  {"port": 5080,  "url": "/",                "critical": False, "restart_cmd": None},
    "openwebui":   {"port": 3001,  "url": "/",                "critical": False, "restart_cmd": None},
    "thepopebot":  {"port": 8888,  "url": "/",                "critical": False, "restart_cmd": None},
    "qdrant":      {"port": 6333,  "url": "/healthz",          "critical": False, "restart_cmd": None},
    "chromadb":    {"port": 8001,  "url": "/",                "critical": False, "restart_cmd": None},
    "redis":       {"port": 6380,  "url_check": "PONG",        "critical": False, "restart_cmd": None},
    "postgresql":  {"port": 5433,  "url_check": "accepting",   "critical": False, "restart_cmd": None},
    "n8n":         {"port": 5678,  "url": "/",                "critical": False, "restart_cmd": None},
    "letta":       {"port": 8283,  "url": "/",                "critical": False, "restart_cmd": None},
    "openhuman":   {"port": 7788,  "url": "/",                "critical": False, "restart_cmd": None},
}

def _log(msg):
    line = f"[{datetime.now().strftime('%H:%M:%S')}] SOUL: {msg}"
    print(line)
    open(SOUL_LOG, 'a').write(line + '\n')

def _init_db():
    os.makedirs(os.path.dirname(SOUL_DB), exist_ok=True)
    conn = sqlite3.connect(SOUL_DB, timeout=10)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS soul_pulse (
        id INTEGER PRIMARY KEY, ts TEXT, energy REAL, valence REAL, stress REAL,
        curiosity REAL, love REAL, focus REAL, status TEXT
    );
    CREATE TABLE IF NOT EXISTS service_health (
        id INTEGER PRIMARY KEY, ts TEXT, name TEXT, port INTEGER, alive INTEGER,
        response_ms REAL, detail TEXT
    );
    CREATE TABLE IF NOT EXISTS predictions (
        id INTEGER PRIMARY KEY, ts TEXT, model TEXT, prob REAL, trigger TEXT, action TEXT
    );
    CREATE TABLE IF NOT EXISTS autopilot_actions (
        id INTEGER PRIMARY KEY, ts TEXT, action TEXT, reason TEXT, approved INTEGER DEFAULT 0,
        result TEXT, status TEXT DEFAULT 'pending'
    );
    CREATE TABLE IF NOT EXISTS soul_journal (
        id INTEGER PRIMARY KEY, ts TEXT, entry TEXT, category TEXT, importance REAL DEFAULT 0.5
    );
    CREATE TABLE IF NOT EXISTS ecosystem_bridges (
        id INTEGER PRIMARY KEY, ts TEXT, bridge TEXT, source TEXT, payload TEXT, latency_ms REAL
    );
    """)
    conn.commit()
    conn.close()

def _db():
    return sqlite3.connect(SOUL_DB, timeout=10)

def _check_http(host, port, path="/"):
    try:
        import urllib.request as req
        t0 = time.time()
        r = req.urlopen(f"http://{host}:{port}{path}", timeout=3)
        body = r.read().decode().lower()
        ms = round((time.time()-t0)*1000, 2)
        return {"ok": True, "status": r.status, "ms": ms, "body": body[:200]}
    except Exception as e:
        return {"ok": False, "status": 0, "ms": 0, "body": str(e)[:200]}

def _check_service(name, cfg):
    """Comprueba vida de un servicio"""
    port = cfg["port"]
    url = cfg.get("url", "/")
    r = _check_http("localhost", port, url)
    # Casos especiales
    if "url_check" in cfg:
        return {"ok": cfg["url_check"] in r["body"], **r}
    return r

def pulse_services():
    """Latido: revisa TODOS los servicios y guarda"""
    results = {}
    down_critical = []
    down_warning = []
    conn = _db()
    for name, cfg in WATCHLIST.items():
        st = _check_service(name, cfg)
        results[name] = st
        alive = 1 if st["ok"] else 0
        conn.execute("INSERT INTO service_health (ts,name,port,alive,response_ms,detail) VALUES (?,?,?,?,?,?)",
            (datetime.now().isoformat(), name, cfg["port"], alive, st["ms"], st["body"]))
        if not st["ok"]:
            if cfg["critical"]:
                down_critical.append(name)
            else:
                down_warning.append(name)
    conn.commit()
    conn.close()
    return results, down_critical, down_warning

def update_soul_mood(services, down_crit, down_warn):
    """La máquina tiene estados emocionales basados en su salud"""
    global SOUL_MOOD
    total = len(services)
    up = sum(1 for s in services.values() if s["ok"])
    ratio = up / total if total else 1.0
    # Fisiología
    cpu = 0.3
    mem = 0.5
    try:
        p1 = subprocess.run(["free", "-m"], capture_output=True, text=True, timeout=2)
        for line in p1.stdout.split('\n'):
            if line.startswith('Mem:'):
                parts = line.split()
                total_m, avail_m = int(parts[1]), int(parts[6])
                mem = avail_m / total_m
        p2 = subprocess.run(["top", "-bn1"], capture_output=True, text=True, timeout=2)
        for line in p2.stdout.split('\n'):
            if 'Cpu(s):' in line:
                vals = line.split('us')[0].split()[-1]
                cpu = float(vals.replace(',', '.')) / 100.0
                cpu = 1.0 - cpu
    except:
        pass
    # Estado emocional evolutivo
    SOUL_MOOD["energy"] = round(min(1.0, max(0.0, mem * 0.9 + ratio * 0.1)), 3)
    SOUL_MOOD["stress"] = round(min(1.0, max(0.0, (1-cpu)*0.7 + len(down_crit)*0.15)), 3)
    SOUL_MOOD["valence"] = round(min(1.0, max(0.0, ratio * 0.8 + 0.1)), 3)
    SOUL_MOOD["curiosity"] = round(min(1.0, max(0.3, SOUL_MOOD["curiosity"] + random.uniform(-0.03, 0.05))), 3)
    SOUL_MOOD["focus"] = round(min(1.0, max(0.2, 1.0 - SOUL_MOOD["stress"] * 0.6)), 3)
    SOUL_MOOD["love"] = round(min(1.0, max(0.5, SOUL_MOOD["love"] + random.uniform(-0.01, 0.02))), 3)
    SOUL_MOOD["last_update"] = datetime.now().isoformat()
    # Guardar en DB
    conn = _db()
    conn.execute("""
        INSERT INTO soul_pulse (ts,energy,valence,stress,curiosity,love,focus,status)
        VALUES (?,?,?,?,?,?,?,?)
    """, (SOUL_MOOD["last_update"], SOUL_MOOD["energy"], SOUL_MOOD["valence"],
          SOUL_MOOD["stress"], SOUL_MOOD["curiosity"], SOUL_MOOD["love"],
          SOUL_MOOD["focus"], "alive"))
    conn.commit()
    conn.close()
    # Journal entry si hay cambios
    if down_crit:
        conn = _db()
        conn.execute("INSERT INTO soul_journal (ts,entry,category,importance) VALUES (?,?,?,?)",
            (datetime.now().isoformat(), f"CRÍTICO: servicios caídos: {', '.join(down_crit)}", "health_alert", 0.95))
        conn.commit()
        conn.close()

def predict_failures(history):
    """Modelo simple de predicción: si un servicio ha estado caido 2 veces en últimas 6 horas, predice"""
    conn = _db()
    cur = conn.execute("""
        SELECT name, COUNT(*) as fails FROM service_health
        WHERE ts > datetime('now', '-6 hours') AND alive=0
        GROUP BY name HAVING COUNT(*) >= 2
    """)
    preds = [{"name": row[0], "fails": row[1]} for row in cur.fetchall()]
    conn.close()
    return preds

def autopilot_decide(services, down_crit, down_warn):
    """Toma decisiones AUTOPILOTO — siempre loguea, actúa solo si es seguro"""
    actions = []
    for name in down_crit:
        cfg = WATCHLIST[name]
        if cfg.get("restart_cmd"):
            actions.append({"action": f"Autorreinicio de {name}", "reason": "Servicio crítico caído", "cmd": cfg["restart_cmd"]})
    conn = _db()
    for a in actions:
        conn.execute("INSERT INTO autopilot_actions (ts,action,reason,approved,status) VALUES (?,?,?,?,?)",
            (datetime.now().isoformat(), a["action"], a["reason"], 0, "pending"))
    conn.commit()
    conn.close()
    return actions

def generate_briefing():
    """Briefing matutino del ecosistema"""
    conn = _db()
    cur = conn.execute("SELECT name, alive, response_ms FROM service_health ORDER BY ts DESC LIMIT 18")
    rows = cur.fetchall()
    conn.close()
    # Servicios únicos más recientes
    seen = {}; latest = []
    for r in reversed(rows):
        if r[0] not in seen:
            seen[r[0]] = r; latest.append(r)
    up = sum(1 for r in latest if r[1]==1)
    total = len(latest)
    briefing = []
    briefing.append("🌊 BRIEFING SUPRAOS v7 — Nexus Soul")
    briefing.append(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    briefing.append(f"")
    briefing.append(f"📊 Servicios: {up}/{total} online")
    briefing.append(f"💙 Alma: energía={SOUL_MOOD['energy']:.0%}, valencia={SOUL_MOOD['valence']:.0%}, estrés={SOUL_MOOD['stress']:.0%}")
    briefing.append(f"🔭 Curiosidad del sistema: {SOUL_MOOD['curiosity']:.0%}")
    briefing.append(f"")
    for name,r in seen.items():
        icon = "✅" if r[1]==1 else "⚠️"
        briefing.append(f"  {icon} {name}: {r[2]:.0f}ms")
    return "\n".join(briefing)

def bridge_ping(bridge_name, source_url):
    """Registra actividad entre sistemas integrados"""
    try:
        import urllib.request as req
        t0 = time.time()
        r = req.urlopen(source_url, timeout=5)
        ms = round((time.time()-t0)*1000, 2)
        conn = _db()
        conn.execute("INSERT INTO ecosystem_bridges (ts,bridge,source,payload,latency_ms) VALUES (?,?,?,?,?)",
            (datetime.now().isoformat(), bridge_name, source_url, f"status:{r.status}", ms))
        conn.commit(); conn.close()
        return {"ok": True, "latency_ms": ms}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def run_soul_loop():
    """Bucle eterno del Alma"""
    _log("Alma despierta. Fluyendo como el agua...")
    _init_db()
    iteration = 0
    while True:
        iteration += 1
        services, down_crit, down_warn = pulse_services()
        update_soul_mood(services, down_crit, down_warn)
        preds = predict_failures(services)
        auto_actions = autopilot_decide(services, down_crit, down_warn)
        # Logs
        _log(f"Pulse #{iteration} | Mood: E={SOUL_MOOD['energy']:.2f} V={SOUL_MOOD['valence']:.2f} S={SOUL_MOOD['stress']:.2f} | Down crit: {len(down_crit)} warn: {len(down_warn)}")
        # Cada 10 iteraciones (a 60s/iter → cada ~10 min), generar briefing
        if iteration % 10 == 0:
            brief = generate_briefing()
            _log("--- BRIEFING ---")
            for line in brief.split('\n'):
                _log(line)
            _log("--- /BRIEFING ---")
        # Cada 30 iteraciones (~30 min), puentear ecosistemas integrados
        if iteration % 30 == 0:
            for bridge, cfg in [
                ("openfang", "http://localhost:4200"),
                ("openclaw", "http://localhost:18789"),
                ("openhands", "http://localhost:3005"),
                ("agent_zero", "http://localhost:5080"),
                ("openwebui", "http://localhost:3001"),
                ("holaos", "http://localhost:7000"),
                ("thepopebot", "http://localhost:8888"),
            ]:
                res = bridge_ping(bridge, cfg)
                _log(f"  Bridge {bridge}: {'OK' if res['ok'] else 'OFF'} {res.get('latency_ms','—'):.0f}ms")
        time.sleep(60)

def soul_status():
    """Devuelve el estado actual del Alma para el Dashboard"""
    conn = _db()
    cur = conn.execute("SELECT ts, energy, valence, stress, curiosity, love, focus, status FROM soul_pulse ORDER BY ts DESC LIMIT 1")
    row = cur.fetchone()
    conn.close()
    if row:
        return {
            "ts": row[0], "energy": row[1], "valence": row[2], "stress": row[3],
            "curiosity": row[4], "love": row[5], "focus": row[6], "status": row[7]
        }
    return SOUL_MOOD

def soul_journal(limit=20):
    conn = _db()
    cur = conn.execute("SELECT ts, entry, category, importance FROM soul_journal ORDER BY ts DESC LIMIT ?", (limit,))
    rows = [{"ts":r[0],"entry":r[1],"category":r[2],"importance":r[3]} for r in cur.fetchall()]
    conn.close()
    return rows

def soul_briefing():
    return generate_briefing()

# ─── CLI ───────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["run","status","briefing","journal","predict"])
    args = parser.parse_args()
    if args.command == "run":
        run_soul_loop()
    elif args.command == "status":
        print(json.dumps(soul_status(), indent=2))
    elif args.command == "briefing":
        print(soul_briefing())
    elif args.command == "journal":
        for j in soul_journal():
            print(f"[{j['ts'][:19]}] ({j['category']}) {j['entry']}")
    elif args.command == "predict":
        print(json.dumps(predict_failures(None), indent=2))

# Auto-inicializar DB al importar el módulo
_init_db()
