#!/usr/bin/env python3
"""
KlawAqua Webhook Event Engine — FASE 5
GitHub push -> auto-pull + re-deploy
Telegram commands -> acciones remotas
Email processor -> Himalaya CLI
"""
import os, json, subprocess, urllib.request as req, sys
from pathlib import Path

KLAWAQUA = "/opt/klawaqua"

def github_webhook(payload):
    """Handler para push de GitHub"""
    try:
        repo_name = payload["repository"]["name"]
        owner = payload["repository"]["owner"]["name"]
        branch = payload["ref"].split("/")[-1]
        commits = payload.get("commits", [])
        
        # Buscar repo local
        local_path = f"{KLAWAQUA}/projects/{repo_name}"
        if not Path(local_path).exists():
            return {"status": "repo_not_local", "repo": repo_name}
        
        # Auto-pull
        r = subprocess.run(["git", "-C", local_path, "pull", "origin", branch],
                          capture_output=True, text=True)
        
        # Detectar si hay docker-compose o restart scripts
        restart = ""
        if Path(f"{local_path}/docker-compose.yml").exists():
            restart = "docker-compose rebuild needed"
        elif Path(f"{local_path}/deploy.sh").exists():
            restart = "deploy.sh found"
        
        return {
            "status": "pulled",
            "repo": repo_name,
            "branch": branch,
            "commits": len(commits),
            "git_output": r.stdout.strip()[-200:] if r.stdout else "n/a",
            "restart_hint": restart
        }
    except Exception as e:
        return {"error": str(e)}

def telegram_webhook(payload):
    """Handler para webhook de Telegram (updates via POST)"""
    try:
        update_id = payload.get("update_id")
        message = payload.get("message", {})
        text = message.get("text", "")
        chat_id = message.get("chat", {}).get("id")
        
        if not text or not chat_id:
            return {"error": "invalid message"}
        
        # Procesar como comando
        result = process_command(text, chat_id)
        return {"status": "processed", "command": text, "result": result}
    except Exception as e:
        return {"error": str(e)}

def process_command(cmd, chat_id):
    """Ejecutar comando remoto en Nexus"""
    cmd = cmd.strip().lower()
    
    if cmd.startswith("/status"):
        try:
            r = req.urlopen("http://localhost:9095/v1/nexus/status", timeout=5)
            return json.loads(r.read())
        except Exception as e:
            return {"error": str(e)}
    
    elif cmd.startswith("/soul"):
        try:
            r = req.urlopen("http://localhost:9095/v1/nexus/soul/status", timeout=5)
            return json.loads(r.read())
        except Exception as e:
            return {"error": str(e)}
    
    elif cmd.startswith("/bridges"):
        try:
            r = req.urlopen("http://localhost:9095/v1/nexus/bridges/list", timeout=5)
            b = json.loads(r.read())["bridges"]
            return {k: v["status"] for k, v in b.items()}
        except Exception as e:
            return {"error": str(e)}
    
    elif cmd.startswith("/chat "):
        msg = cmd[6:]  # despues de /chat
        sys.path.insert(0, f"{KLAWAQUA}/scripts")
        try:
            import kaiya_soul_bridge as kaiya
            return {"reply": kaiya.process_message(msg)}
        except Exception as e:
            return {"error": str(e)}
    
    elif cmd.startswith("/backup"):
        subprocess.run(["python3", f"{KLAWAQUA}/scripts/klawaqua_backup.py", "all"],
                      capture_output=True, text=True)
        return {"status": "backup_started"}
    
    elif cmd.startswith("/vision"):
        return {"status": "use /vision <URL_image> via Telegram Bot"}
    
    else:
        return {"status": "unknown_command", "help": "/status /soul /bridges /chat /backup"}

# ─── CLI ────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["github", "telegram"])
    parser.add_argument("--payload", default="{}")
    args = parser.parse_args()
    
    payload = json.loads(args.payload)
    
    if args.command == "github":
        print(json.dumps(github_webhook(payload), indent=2))
    elif args.command == "telegram":
        print(json.dumps(telegram_webhook(payload), indent=2))
