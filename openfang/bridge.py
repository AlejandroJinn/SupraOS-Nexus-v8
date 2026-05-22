#!/usr/bin/env python3
"""OpenFang Bridge Server - :4200 - Sin dependencia toml"""
import json, urllib.request, time
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = 4200
DEFAULT_MODEL = "qwen3:4b"
AGENTS = [{"name":"klawaqua-assistant","model":"qwen3:4b","provider":"ollama"},
          {"name":"klawaqua-reasoner","model":"qwen3.5:4b","provider":"ollama"},
          {"name":"klawaqua-coder","model":"qwen2.5-coder:1.5b","provider":"ollama"}]

def proxy(prompt, model=DEFAULT_MODEL):
    try:
        b = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
        req = urllib.request.Request("http://localhost:11434/api/generate", b, headers={"Content-Type":"application/json"})
        r = urllib.request.urlopen(req, timeout=60)
        return json.loads(r.read()).get("response", "(empty)")
    except Exception as e: return f"[OpenFang Error] {e}"

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Type","application/json"); self.send_header("Access-Control-Allow-Origin","*"); self.end_headers()
        if self.path == "/health": d = {"status":"alive","version":"0.1.0","agents":len(AGENTS),"model":DEFAULT_MODEL}
        elif self.path == "/agents": d = {"agents":AGENTS}
        elif self.path == "/status": d = {"status":"online","bridge":"OpenFang","port":PORT,"timestamp":time.strftime("%Y-%m-%dT%H:%M:%S")}
        else: d = {"ok":True,"bridge":"OpenFang","routes":["/health","/agents","/status","/chat (POST)"]}
        self.wfile.write(json.dumps(d).encode())
    def do_POST(self):
        self.send_response(200); self.send_header("Content-Type","application/json"); self.send_header("Access-Control-Allow-Origin","*"); self.end_headers()
        if self.path == "/chat":
            try:
                l = int(self.headers.get("Content-Length",0))
                body = json.loads(self.rfile.read(l)) if l else {}
                resp = proxy(body.get("prompt",body.get("message","")), body.get("model",DEFAULT_MODEL))
                d = {"reply":resp,"model":body.get("model",DEFAULT_MODEL),"bridge":"OpenFang"}
            except Exception as e: d = {"error":str(e)}
        else: d = {"ok":False,"msg":"unsupported"}
        self.wfile.write(json.dumps(d).encode())
    def log_message(self, format, *a): pass

if __name__ == "__main__":
    print(f"[OpenFang] Bridge :{PORT}")
    HTTPServer(("0.0.0.0",PORT),H).serve_forever()
