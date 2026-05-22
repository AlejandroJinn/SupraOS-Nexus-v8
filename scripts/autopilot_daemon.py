#!/usr/bin/env python3
"""
KlawAqua Autopilot Daemon v7 — Autodiag + Resumen 12h + Alertas Telegram
Monitoreo de salud, generacion de briefings y notificacion remota.
"""
import os, sys, json, time, sqlite3, datetime, subprocess, urllib.request as req
from pathlib import Path

KLAWAQUA = "/opt/klawaqua"
DB = f"{KLAWAQUA}/data/autopilot.db"
LOG_DIR = "/tmp"
NEXUS = "http://localhost:9095"
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8469591478:AAGjPrpL5XR7Igh0fqp-JeL6Tma8NMEDEy8")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")  # Se configura al primer /start

def _init_db():
    Path(DB).parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB)
    c.execute("""
        CREATE TABLE IF NOT EXISTS health_log (
            id INTEGER PRIMARY KEY,
            ts TEXT,
            metric TEXT,
            value REAL,
            status TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY,
            ts TEXT,
            task TEXT,
            result TEXT,
            status TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS chat_id (
            id INTEGER PRIMARY KEY,
            chat_id TEXT,
            username TEXT,
            ts TEXT
        )
    """)
    c.commit(); c.close()

def _db():
    return sqlite3.connect(DB)

# ─── Health Collection ──────────────────────────────────────
def check_all():
    results = {}
    services = {
        "Nexus": "http://localhost:9095/v1/nexus/status",
        "GPU llama": "http://localhost:8085",
        "Router": "http://localhost:9000",
        "OpenClaw": "http://localhost:18789/healthz",
        "OpenHands": "http://localhost:3005",
        "AgentZero": "http://localhost:5080",
        "OpenFang": "http://localhost:4200/health",
        "OpenSwarm": "http://localhost:8765/health",
        "ThePopeBot": "http://localhost:8888/health",
        "OpenWebUI": "http://localhost:3001",
    }
    for name, url in services.items():
        try:
            req.urlopen(url, timeout=5)
            status = "online"
        except Exception:
            status = "offline"
        results[name] = status
    
    # Guardar en DB
    c = _db()
    now = datetime.datetime.now().isoformat()
    for k, v in results.items():
        c.execute("INSERT INTO health_log(ts,metric,value,status) VALUES(?,?,?,?)",
                  (now, k, 1.0 if v == "online" else 0.0, v))
    c.commit(); c.close()
    return results

# ─── System Stats ───────────────────────────────────────────
def get_system_stats():
    # CPU desde /proc/stat
    try:
        with open("/proc/stat") as f:
            line = f.readline()
        fields = line.split()
        user, nice, system, idle = int(fields[1]), int(fields[2]), int(fields[3]), int(fields[4])
        total = user + nice + system + idle
        # Leer guardado anterior
        prev_file = "/tmp/.autopilot_cpu_prev"
        if os.path.exists(prev_file):
            with open(prev_file) as f:
                p = json.load(f)
            total_d = total - p["total"]
            idle_d = idle - p["idle"]
            cpu = 100.0 * (total_d - idle_d) / total_d if total_d else 0.0
        else:
            cpu = 0.0
        with open(prev_file, "w") as f:
            json.dump({"total": total, "idle": idle}, f)
    except Exception:
        cpu = 0.0
    
    # RAM desde /proc/meminfo
    try:
        vals = {}
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    vals["total"] = int(line.split()[1])  # kB
                elif line.startswith("MemAvailable:"):
                    vals["avail"] = int(line.split()[1])
        mem = 100.0 * (vals["total"] - vals["avail"]) / vals["total"] if vals.get("total") else 0.0
    except Exception:
        mem = 0.0
    
    # Disk
    try:
        disk_root = subprocess.check_output("df -h / | tail -1 | awk '{print $5}'", shell=True).decode().strip().rstrip("%")
        disk = float(disk_root) if disk_root else 0.0
    except Exception:
        disk = 0.0
    try:
        disk_ssd = subprocess.check_output("df -h /run/media/clarwis/SSD 2>/dev/null | tail -1 | awk '{print $5}'", shell=True).decode().strip().rstrip("%")
        ssd = float(disk_ssd) if disk_ssd else 0.0
    except Exception:
        ssd = 0.0
    
    return {"cpu": cpu, "mem": mem, "disk_root": disk, "disk_usb_ssd": ssd}

# ─── Briefing Generation ──────────────────────────────────
def generate_briefing(check_results=None):
    if check_results is None:
        check_results = check_all()
    stats = get_system_stats()
    total = len(check_results)
    online = sum(1 for v in check_results.values() if v == "online")
    offline = [(k, v) for k, v in check_results.items() if v == "offline"]
    
    # Generar texto KAIYA-like
    lines = [
        f"🌊 *SUPRAOS v7 — Briefing Automatico*", "",
        f"⏰ *Hora:* {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}", "",
        f"📊 *Servicios:* {online}/{total} online",
    ]
    if offline:
        lines.append(f"⚠️ *Offline:* {', '.join([k for k,_ in offline])}")
    lines.extend([
        "",
        f"⚡ *CPU:* {stats['cpu']:.1f}%",
        f"💾 *RAM:* {stats['mem']:.1f}%",
        f"💿 *Sistema:* {stats['disk_root']:.0f}%",
    ])
    if stats['disk_usb_ssd'] > 0:
        lines.append(f"🔌 *USB SSD 2TB:* {stats['disk_usb_ssd']:.0f}% usado")
    
    # Jobs del Autopilot
    c = _db()
    rows = c.execute("SELECT ts, task, status FROM jobs ORDER BY id DESC LIMIT 5").fetchall()
    c.close()
    if rows:
        lines.append("")
        lines.append("🛠️ *Trabajos recientes:*")
        for r in rows:
            lines.append(f"  • {r[0][:16]}: {r[1]} [{r[2]}]")
    
    lines.extend(["", "💙 *_Fluye como el agua_*"])
    return "\n".join(lines)

# ─── Telegram Send ──────────────────────────────────────────
def send_telegram(text):
    if not TELEGRAM_TOKEN:
        return {"error": "No TELEGRAM_TOKEN"}
    # Obtener chat_id registrado
    c = _db()
    row = c.execute("SELECT chat_id FROM chat_id ORDER BY id DESC LIMIT 1").fetchone()
    c.close()
    cid = CHAT_ID or (row[0] if row else "")
    if not cid:
        return {"error": "No Telegram CHAT_ID configured. Send /start to the bot first."}
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    body = json.dumps({"chat_id": cid, "text": text, "parse_mode": "Markdown"}).encode()
    try:
        r = req.urlopen(req.Request(url, body, headers={"Content-Type": "application/json"}), timeout=10)
        return {"ok": True, "sent": True}
    except Exception as e:
        return {"error": str(e)}

def register_chat(chat_id, username=""):
    c = _db()
    now = datetime.datetime.now().isoformat()
    c.execute("INSERT OR REPLACE INTO chat_id(id, chat_id, username, ts) VALUES(1,?,?,?)", (str(chat_id), username, now))
    c.commit(); c.close()
    return {"ok": True, "chat_id": chat_id}

def get_status_last_24h():
    """Devuelve evolucion de servicios en ultimas 24h"""
    c = _db()
    cutoff = (datetime.datetime.now() - datetime.timedelta(hours=24)).isoformat()
    rows = c.execute("""
        SELECT metric, 
               AVG(CASE WHEN status='online' THEN 1 ELSE 0 END) as uptime_pct,
               COUNT(*) as checks
        FROM health_log 
        WHERE ts > ? 
        GROUP BY metric
    """, (cutoff,)).fetchall()
    c.close()
    return {r[0]: {"uptime_24h": r[1]*100, "checks": r[2]} for r in rows}

# ─── CLI ────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Autopilot Daemon")
    parser.add_argument("command", choices=["check", "briefing", "briefing-send", "stats", "loop", "register-chat"])
    parser.add_argument("--chat-id", default="")
    parser.add_argument("--username", default="")
    args = parser.parse_args()
    
    _init_db()
    
    if args.command == "check":
        results = check_all()
        print(json.dumps(results, indent=2))
    elif args.command == "stats":
        print(json.dumps(get_system_stats(), indent=2))
    elif args.command == "briefing":
        print(generate_briefing())
    elif args.command == "briefing-send":
        # Guardar briefing como job
        text = generate_briefing()
        c = _db()
        c.execute("INSERT INTO jobs(ts, task, result, status) VALUES(?,?,?)",
                  (datetime.datetime.now().isoformat(), "briefing-generado", text[:500], "ok"))
        c.commit(); c.close()
        result = send_telegram(text)
        print(json.dumps(result))
    elif args.command == "register-chat":
        if args.chat_id:
            print(json.dumps(register_chat(args.chat_id, args.username)))
        else:
            print("Usage: autopilot_daemon.py register-chat --chat-id 123456789")
    elif args.command == "loop":
        print("[Autopilot] Loop iniciado. Reportes cada 12h. Ctrl+C para salir.")
        interval = 43200  # 12 horas
        while True:
            print(f"[{datetime.datetime.now().strftime('%H:%M')}] Ciclo de salud...")
            check_all()
            # Cada 12h generar y enviar briefing
            text = generate_briefing()
            c = _db()
            c.execute("INSERT INTO jobs(ts, task, result, status) VALUES(?,?,?,?)",
                      (datetime.datetime.now().isoformat(), "briefing-auto", text[:500], "ok"))
            c.commit(); c.close()
            send_telegram(text)
            print(f"  Briefing enviado. Durmiendo {interval/3600:.0f}h...")
            time.sleep(interval)
