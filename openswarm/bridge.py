#!/usr/bin/env python3
"""
OpenSwarm Bridge Server — KlawAqua Nexus Integration
Expone /health + /status + /swarm en :8765
Integra con Ollama local (:11434) via LLM
"""
import json, urllib.request, os, time
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = 8765
DEFAULT_MODEL = os.getenv("OPENSWARM_MODEL", "llama3.2")

def proxy_ollama(prompt, model=None):
    m = model or DEFAULT_MODEL
    try:
        body = json.dumps({"model": m, "prompt": prompt, "stream": False}).encode()
        req = urllib.request.Request("http://localhost:11434/api/generate", body, headers={"Content-Type": "application/json"})
        r = urllib.request.urlopen(req, timeout=60)
        return json.loads(r.read()).get("response", "(sin respuesta)")
    except Exception as e:
        return f"[OpenSwarm Error] {e}"

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if self.path == "/health" or self.path == "/":
            out = {"status": "alive", "version": "0.1.0a1", "bridge": "OpenSwarm", "model": DEFAULT_MODEL}
        elif self.path == "/status":
            out = {"status": "online", "bridge": "OpenSwarm", "port": PORT, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")}
        else:
            out = {"ok": True, "bridge": "OpenSwarm", "routes": ["/health", "/status", "/chat (POST)"]}
        self.wfile.write(json.dumps(out).encode())

    def do_POST(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if self.path == "/chat":
            try:
                l = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(l)) if l else {}
                prompt = body.get("prompt", body.get("message", ""))
                model = body.get("model", DEFAULT_MODEL)
                resp = proxy_ollama(prompt, model)
                out = {"reply": resp, "model": model, "bridge": "OpenSwarm"}
            except Exception as e:
                out = {"error": str(e)}
        else:
            out = {"ok": False, "msg": "Ruta no soportada"}
        self.wfile.write(json.dumps(out).encode())

    def log_message(self, format, *a): pass

if __name__ == "__main__":
    print(f"[OpenSwarm] Bridge iniciado en :{PORT}")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
