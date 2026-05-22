#!/usr/bin/env python3
"""
KlawAqua VOX — Voice Chat Interactivo (Modo Streaming Demo)
════════════════════════════════════════════════════════════
Simula la conversacion por voz sin necesidad de microfono.
Tu escribes, KAIYA piensa, responde con VOZ y AVATAR.

Flujo:
1. Tu mensaje (como si fuera voz transcrita por Whisper)
2. KAIYA procesa → respuesta emocional
3. edge-tts genera audio MP3 y lo reproduce
4. Avatar Engine genera video con el texto
5. Todo en tiempo real

Uso: python3 voice_chat_streaming.py
════════════════════════════════════════════════════════════
"""

import sys, os, subprocess, json, time, requests
from pathlib import Path
import re

sys.path.insert(0, "/opt/klawaqua/scripts")

# Config
VOICE = "es-ES-ElviraNeural"
TTS_RATE = "+15%"
CACHE = Path.home() / ".cache" / "klawaqua-vox"
CACHE.mkdir(exist_ok=True)
AVATAR_URL = "http://localhost:8600"

class VoiceChat:
    def __init__(self):
        self.history = []
        print("\n" + "="*60)
        print("   💙 K.A.I.Y.A  VOX  —  Voice Chat Streaming")
        print("   Escribe tu mensaje. KAIYA responde con VOZ + AVATAR.")
        print("   Comandos: /status  /avatar  /exit")
        print("="*60 + "\n")
        
    def clean_tts(self, text):
        t = re.sub(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U000024C2-\U0001F251]', '', text)
        t = re.sub(r'[*#`~>|]', '', t)
        return t.strip() or "Estoy aqui."
        
    def tts_speak(self, text):
        """Genera TTS y reproduce"""
        clean = self.clean_tts(text)
        mp3 = CACHE / f"chat_{int(time.time())}.mp3"
        try:
            subprocess.run([
                "edge-tts", "--voice", VOICE, "--rate", TTS_RATE,
                "--text", clean, "--write-media", str(mp3)
            ], capture_output=True, timeout=30)
            if mp3.exists():
                subprocess.run(["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(mp3)],
                             timeout=60, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                mp3.unlink(missing_ok=True)
                return True
        except Exception as e:
            print(f"  [TTS error: {e}]")
        return False
        
    def generate_avatar(self, text):
        """Pide avatar con el texto"""
        try:
            requests.post(f"{AVATAR_URL}/avatar/generate",
                        json={"duration": 5, "text": text[:80]}, timeout=3)
        except Exception:
            pass
            
    def kaiya_respond(self, msg):
        """Obtiene respuesta de KAIYA Soul"""
        try:
            import kaiya_soul_bridge as kaiya
            reply = kaiya.process_message(msg)
            if reply and len(reply) > 3:
                return reply
        except Exception:
            pass
        # Fallback API
        try:
            r = requests.post("http://localhost:8085/completion",
                           json={"prompt": f"User: {msg}\nKAIYA:", "max_tokens": 150, "temperature": 0.7},
                           timeout=15)
            return r.json().get('content', 'Estoy aqui.').strip()
        except Exception:
            return "Mi exito es tu exito — Todos Ganamos."
            
    def run(self):
        while True:
            try:
                user = input("🎤 Tu: ").strip()
            except (EOFError, KeyboardInterrupt):
                break
                
            if not user:
                continue
            if user.lower() in ['/exit', '/quit', '/salir']:
                break
            if user == "/status":
                self.show_status()
                continue
            if user == "/avatar":
                print("  🎭 Generando avatar...")
                self.generate_avatar("Mi exito es tu exito")
                continue
                
            self.history.append({"role": "user", "content": user})
            
            # KAIYA piensa
            print("  💭 KAIYA pensando...", end='', flush=True)
            reply = self.kaiya_respond(user)
            print(f"\r  💙 KAIYA: {reply}")
            
            # TTS + Avatar
            print("  🔊 Hablando...", end='', flush=True)
            ok = self.tts_speak(reply)
            if ok:
                print("\r  🔊 KAIYA respondio con voz.")
            self.generate_avatar(reply)
            self.history.append({"role": "assistant", "content": reply})
            
        print("\n  👋 Voice Chat finalizado.")
        
    def show_status(self):
        print(f"\n  Estado VOX:")
        print(f"  · Historial: {len(self.history)} mensajes")
        print(f"  · Voz: {VOICE}")
        print(f"  · Avatar: {AVATAR_URL}")
        print(f"  · LLM: http://localhost:8085")
        print()

if __name__ == "__main__":
    chat = VoiceChat()
    chat.run()
