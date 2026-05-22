#!/usr/bin/env python3
"""
KlawAqua VideoCall Server — Endpoint /voice/chat
══════════════════════════════════════════════════════
Recibe audio (webm/base64), lo transcribe con Whisper, genera respuesta KAIYA + TTS

Uso: python3 videocall_server.py
Puerto: :8601 (separado del avatar engine :8600)
"""

import os, sys, json, base64, subprocess, tempfile, time, re
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests

sys.path.insert(0, "/opt/klawaqua/scripts")

VOICE = "es-ES-ElviraNeural"
TTS_RATE = "+15%"
CACHE = Path.home() / ".cache" / "klawaqua-vox"
CACHE.mkdir(exist_ok=True)
AVATAR_URL = "http://localhost:8600"

import whisper

# Cargar modelo Whisper una vez
print("📥 Cargando modelo Whisper base...")
WHISPER = whisper.load_model("base")

def clean_tts(text):
    t = re.sub(r'[\U0001F600-\U0001F6FF]', '', text)
    t = re.sub(r'[*#`~>]', '', t)
    return t.strip() or "Estoy aqui."

def transcribe_audio(webm_path):
    """Transcribe audio con Whisper local"""
    try:
        result = WHISPER.transcribe(webm_path, language="es", fp16=False)
        text = result.get("text", "").strip()
        # Eliminar archivos temporales
        webm_path.unlink(missing_ok=True)
        return text
    except Exception as e:
        print(f"Whisper error: {e}")
        return ""

def kaiya_respond(msg):
    """Obtiene respuesta de KAIYA Soul"""
    try:
        import kaiya_soul_bridge as kaiya
        return kaiya.process_message(msg)
    except Exception:
        pass
    # Fallback a llama.cpp
    try:
        r = requests.post("http://localhost:8085/completion",
                         json={"prompt": f"User: {msg}\nKAIYA:", "max_tokens": 150, "temperature": 0.7},
                         timeout=15)
        return r.json().get('content', 'Estoy aqui.').strip()
    except:
        return "Mi exito es tu exito — Todos Ganamos."

def tts_generate(text):
    """Genera TTS y devuelve audio como base64"""
    clean = clean_tts(text)
    mp3 = CACHE / f"vc_{int(time.time())}.mp3"
    try:
        subprocess.run([
            "edge-tts", "--voice", VOICE, "--rate", TTS_RATE,
            "--text", clean, "--write-media", str(mp3)
        ], capture_output=True, timeout=30)
        if mp3.exists():
            with open(mp3, 'rb') as f:
                data = base64.b64encode(f.read()).decode()
            mp3.unlink(missing_ok=True)
            return data
    except Exception as e:
        print(f"TTS error: {e}")
    return None

def generate_avatar(text):
    """Trigger avatar generation"""
    try:
        requests.post(f"{AVATAR_URL}/avatar/generate",
                    json={"duration": 5, "text": text[:80]}, timeout=3)
    except:
        pass

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *a): pass
    
    def _json(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())
    
    def do_OPTIONS(self):
        self._json(200, {"ok": True})
    
    def do_POST(self):
        if self.path == "/voice/chat":
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(content_length).decode('utf-8')
                data = json.loads(body)
                
                audio_b64 = data.get('audio', '')
                if not audio_b64:
                    self._json(400, {"error": "No audio provided"})
                    return
                
                # Guardar audio webm
                webm_data = base64.b64decode(audio_b64)
                webm_path = CACHE / f"input_{int(time.time())}.webm"
                with open(webm_path, 'wb') as f:
                    f.write(webm_data)
                
                # → STT
                print(f"🎤 Audio recibido: {len(webm_data)} bytes")
                text = transcribe_audio(webm_path)
                print(f"🗣️  Transcripción: {text}")
                
                if not text:
                    self._json(200, {"transcription": "", "reply": "No pude escucharte bien. ¿Puedes repetir?", "audio": None})
                    return
                
                # → KAIYA
                reply = kaiya_respond(text)
                print(f"💙 KAIYA: {reply[:60]}...")
                
                # → TTS
                audio_b64 = tts_generate(reply)
                
                # → Avatar
                generate_avatar(reply)
                
                self._json(200, {
                    "transcription": text,
                    "reply": reply,
                    "audio": audio_b64
                })
                
            except Exception as e:
                import traceback
                traceback.print_exc()
                self._json(500, {"error": str(e)})
        else:
            self._json(404, {"error": "Not found"})

if __name__ == "__main__":
    PORT = 8601
    print(f"📹 KlawAqua VideoCall Server en :{PORT}")
    print(f"   Endpoint POST http://localhost:{PORT}/voice/chat")
    print(f"   Whisper base cargado. Listo para videollamadas.\n")
    
    srv = HTTPServer(("", PORT), Handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 VideoCall server terminado.")
