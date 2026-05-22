#!/usr/bin/env python3
"""
KlawAqua Avatar Engine v1 — Generador 100% local con FFmpeg
Toma la imagen de la Guerrera y genera videos de avatar con efectos de ondas
Integración: Dashboard v8 + API Nexus + Telegram
"""
import subprocess, json, os, random, tempfile, shutil
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

AVATAR_IMAGE = os.environ.get("AVATAR_SOURCE", "/home/clarwis/Descargas/photo_2026-04-21_15-52-21.jpg")
OUTPUT_DIR = Path("/opt/klawaqua/data/avatars")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def generate_avatar_video(duration=5, text="", tinte=True):
    """Genera video avatar con efecto de onda acuatica suave"""
    if not Path(AVATAR_IMAGE).exists():
        return {"error": f"Imagen no encontrada: {AVATAR_IMAGE}"}
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = OUTPUT_DIR / f"avatar_{timestamp}.mp4"
    
    # Preparar imagen base redimensionada
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        img_tmp = tmp.name
    
    subprocess.run([
        "ffmpeg", "-y", "-i", AVATAR_IMAGE,
        "-vf", "scale=1080:1920:flags=lanczos:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,format=yuv420p",
        "-frames:v", "1",
        img_tmp
    ], capture_output=True, check=True)
    
    # Construir filtro: tinte azul + texto + fade
    vf_parts = [
        "scale=1080:1920:flags=lanczos",
    ]
    
    if tinte:
        # tinte azul acuatico sutil via colorbalance
        vf_parts.append("colorbalance=bs=0.25")  # boost azul
    
    # Texto
    if text:
        esc = text.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")
        font = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if not Path(font).exists():
            font = "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"
            if not Path(font).exists():
                font = "sans"
        vf_parts.append(
            f"drawtext=text='{esc}':fontcolor=white:fontsize=52:"
            f"fontfile={font}:x=(w-text_w)/2:y=h*0.82:"
            f"borderw=4:bordercolor=black@0.8:shadowx=2:shadowy=2"
        )
    
    vf_parts.append(f"fade=t=out:st={duration-1}:d=1,format=yuv420p")
    
    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-i", img_tmp,
        "-vf", ",".join(vf_parts),
        "-t", str(duration),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-preset", "ultrafast", "-crf", "28", "-movflags", "+faststart",
        str(output_path)
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            return {"error": f"FFmpeg: {result.stderr[:300]}"}
        
        size_mb = output_path.stat().st_size / (1024*1024)
        return {
            "path": str(output_path), "size_mb": round(size_mb, 2),
            "duration": duration, "text": text or None,
            "timestamp": timestamp, "generated_at": datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": str(e)}
    finally:
        if Path(img_tmp).exists():
            Path(img_tmp).unlink()

# ─── HTTP Server ──────────────────────────────────────────────
PORT = 8600

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *a): pass
    
    def _json(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, indent=2).encode())
    
    def do_GET(self):
        if self.path == "/health":
            self._json(200, {"status": "alive", "avatar": AVATAR_IMAGE, "engine": "ffmpeg-local"})
        elif self.path == "/avatar/latest":
            files = sorted(OUTPUT_DIR.glob("avatar_*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
            if files:
                self.send_response(200)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                with open(files[0], "rb") as f:
                    shutil.copyfileobj(f, self.wfile)
            else:
                self._json(404, {"error": "No hay videos generados aun"})
        elif self.path == "/avatar/list":
            files = sorted(OUTPUT_DIR.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)[:20]
            items = [{"name": f.name, "size_mb": round(f.stat().st_size/(1024*1024),2),
                      "created": datetime.fromtimestamp(f.stat().st_mtime).isoformat()} for f in files]
            self._json(200, {"avatars": items, "total": len(items)})
        else:
            self._json(404, {"error": "Unknown endpoint"})
    
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n).decode() if n else "{}"
        data = json.loads(body) if body else {}
        
        if self.path == "/avatar/generate":
            duration = data.get("duration", 5)
            text = data.get("text", "")
            result = generate_avatar_video(duration=duration, text=text)
            self._json(200 if "error" not in result else 500, result)
        else:
            self._json(404, {"error": "Unknown endpoint"})
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

if __name__ == "__main__":
    print(f"[Avatar Engine] :{PORT} — Fuente: {AVATAR_IMAGE}")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
