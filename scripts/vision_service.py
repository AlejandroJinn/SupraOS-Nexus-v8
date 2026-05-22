#!/usr/bin/env python3
"""
KlawAqua Vision Service — MiniCPM-V:4.6 via llama.cpp
Servidor HTTP :8090 que analiza imágenes con visión local 100%
"""
import os, sys, json, subprocess, tempfile, time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

PORT = 8090
LLAMA_SERVER = os.path.expanduser("~/llama.cpp/build/bin/llama-server")
MODEL = "/opt/klawaqua/models/minicpm/MiniCPM-V-4_6-Q4_K_M.gguf"
MMPROJ = "/opt/klawaqua/models/minicpm/mmproj-MiniCPM-V-4.6-Q8_0.gguf"

def is_server_running():
    try:
        import urllib.request as req
        req.urlopen("http://localhost:8090/health", timeout=2)
        return True
    except: return False

def start_llama_vision_server():
    if is_server_running():
        print("[Vision] :8090 ya en uso -> reutilizando"); return
    if not Path(LLAMA_SERVER).exists():
        print(f"[Vision] ERROR: {LLAMA_SERVER} no existe"); return
    if not Path(MODEL).exists():
        print(f"[Vision] ERROR: modelo no existe"); return
    cmd = [LLAMA_SERVER, "-m", MODEL, "--mmproj", MMPROJ,
           "--host", "0.0.0.0", "--port", str(PORT),
           "-c", "8192", "-ngl", "999"]
    subprocess.Popen(cmd, stdout=open("/tmp/vision_server.log","w"), stderr=subprocess.STDOUT)
    print(f"[Vision] llama-server vision iniciando en :{PORT}")
    for _ in range(15):
        time.sleep(1)
        try:
            import urllib.request as req
            req.urlopen("http://localhost:8090/health", timeout=2)
            print("[Vision] Vision server online"); return
        except: pass
    print("[Vision] No respondio aun")

def analyze_image(image_path, prompt="Describe la imagen"):
    try:
        import urllib.request as req, base64
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        msg = [{"type":"image_url", "image_url":{"url":"data:image/jpeg;base64,"+b64}},
               {"type":"text", "text":prompt}]
        body = json.dumps({
            "model":"minicpm-v",
            "messages":[{"role":"user","content":msg}],
            "temperature":0.4, "max_tokens":512
        }).encode()
        rq = req.Request("http://localhost:8090/v1/chat/completions",
                         body, headers={"Content-Type":"application/json"})
        r = req.urlopen(rq, timeout=120)
        d = json.loads(r.read())
        return d["choices"][0]["message"]["content"]
    except Exception as e:
        return f"[Vision Error] {e}"

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers()
        self.wfile.write("{\"status\":\"alive\",\"model\":\"MiniCPM-V-4.6\",\"gpu\":true}".encode())
    def do_POST(self):
        self.send_response(200)
        self.send_header("Content-Type","application/json")
        self.send_header("Access-Control-Allow-Origin","*")
        self.end_headers()
        if self.path == "/analyze":
            try:
                l = int(self.headers.get("Content-Length",0))
                body = json.loads(self.rfile.read(l)) if l else {}
                img = body.get("image_path","")
                prompt = body.get("prompt","Describe la imagen")
                if not img or not Path(img).exists():
                    d = {"error":"image_path invalido"}
                else:
                    desc = analyze_image(img, prompt)
                    d = {"description":desc,"model":"MiniCPM-V-4.6"}
            except Exception as e: d = {"error":str(e)}
        else:
            d = {"error":"usa /analyze"}
        self.wfile.write(json.dumps(d).encode())
    def log_message(self, format, *a): pass

if __name__ == "__main__":
    start_llama_vision_server()
    print(f"[Vision] HTTP :{PORT} listo")
    HTTPServer(("0.0.0.0",PORT),H).serve_forever()
