#!/usr/bin/env python3
"""
KlawAqua Router Watchdog
Verifica router + Ollama cada 30s, auto-recovery si algo cae
"""

import subprocess, time, json, sys, os
from datetime import datetime

ROUTER_URL = "http://localhost:9000/api/v1/status"
OLLAMA_URL = "http://localhost:11434/"
LOG_FILE = "/opt/klawaqua/logs/watchdog.log"
MAX_RETRIES = 3
RETRY_DELAY = 5

def log(msg, level="OK"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {level}: {msg}"
    print(line, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a") as f: f.write(line + "\n")
    except: pass

def curl(url, timeout=3):
    try:
        r = subprocess.run(["curl", "-s", "-m", str(timeout), url], 
            capture_output=True, text=True, timeout=timeout+2)
        return r.stdout.strip(), r.returncode == 0
    except:
        return "", False

def check_ollama():
    """Verifica que Ollama responde"""
    _, ok = curl(OLLAMA_URL)
    return ok

def check_router():
    """Verifica router HTTP"""
    out, ok = curl(ROUTER_URL)
    if not ok:
        return False, "down"
    try:
        d = json.loads(out)
        # KlawAqua kernel returns "online": int, not "status":"ok"
        if d.get("online") is not None:
            return True, d
        if d.get("status") == "ok":
            return True, d
    except: pass
    return False, out

def restart_service(name, cmd):
    """Mata proceso viejo, arranca nuevo"""
    log(f"Reiniciando {name}...", "WARN")
    subprocess.run(["pkill", "-f", name], capture_output=True)
    time.sleep(2)
    try:
        subprocess.Popen(cmd, 
            stdout=open(LOG_FILE, "a"),
            stderr=subprocess.STDOUT,
            start_new_session=True)
        log(f"{name} reiniciado", "OK")
        return True
    except Exception as e:
        log(f"Error reiniciando {name}: {e}", "ERROR")
        return False

def main():
    """Loop principal del watchdog"""
    log("Watchdog iniciado")
    while True:
        # Check Ollama
        if not check_ollama():
            log("Ollama caido - intentando recovery")
            subprocess.run(["systemctl", "restart", "ollama"], 
                capture_output=True, timeout=10)
            time.sleep(5)
            if not check_ollama():
                # Intento 2: forzar pkill
                subprocess.run(["pkill", "-9", "ollama"], capture_output=True)
                time.sleep(2)
                subprocess.Popen(["ollama", "serve"], 
                    stdout=open(LOG_FILE, "a"), stderr=subprocess.STDOUT,
                    start_new_session=True)
                time.sleep(5)
        
        # Check Router Service  
        ok, data = check_router()
        if not ok:
            log(f"Router caido - restarting")
            restart_service("router_service.py",
                ["python3", "/opt/klawaqua/scripts/router_service.py"])
            time.sleep(3)
            ok2, _ = check_router()
            if not ok2:
                log("Router no recovery despues de reinicio", "ERROR")
        else:
            local = data.get("local_model", "?")
            log(f"OK | Mode: {data.get('mode','?')} | Local: {local}")
        
        time.sleep(30)  # Check cada 30 segundos

if __name__ == "__main__":
    main()
