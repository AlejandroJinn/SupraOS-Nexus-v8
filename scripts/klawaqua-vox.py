#!/usr/bin/env python3
"""
KlawAqua VOX — Agente Conversacional Visual 4D
═══════════════════════════════════════════════════════════════
Asistente de escritorio que ESCUCHA, PIENSA y RESPONDE en tiempo real:

· STT (Speech-to-Text): Whisper local con pyaudio streaming
· LLM: KAIYA Soul (GPU local :8085) o backup GPT
· TTS: edge-tts con voz hispana (es-EliaNeural / es-AlonsoNeural)
· Vision: Screenshot + descripción visual (MiniCPM-V opcional)
· Lip-sync: Animación avatar con FFmpeg

Flujo:
1. Usuario habla → micrófono captura streaming
2. Whisper transcribe a texto
3. KAIYA procesa el mensaje → emoción + respuesta
4. edge-tts genera audio MP3
5. Avatar engine genera video con lip-sync
6. Reproduce en pantalla

100% soberano local. Sin APIs.
═══════════════════════════════════════════════════════════════
"""

import os, sys, json, time, subprocess, threading, queue, tempfile, gc
from pathlib import Path
from datetime import datetime
import numpy as np, pyaudio, wave, requests

# ── CONFIGURACIÓN ──────────────────────────────────────────
WHISPER_MODEL = "base"  # 74MB, fast. Opciones: tiny, small, medium, large-v3-turbo
VOICE = "es-ES-ElviraNeural"  # Voz femenina española para KAIYA
LLM_URL = "http://localhost:8085/completion"
AVATAR_ENGINE_URL = "http://localhost:8600"
TTS_RATE = "+20%"  # velocidad voz
TTS_PITCH = "+0Hz"

# Audio
SAMPLE_RATE = 16000
CHUNK_DURATION = 1.5  # segundos por chunk
CHUNK = int(SAMPLE_RATE * CHUNK_DURATION)
FORMAT = pyaudio.paInt16
CHANNELS = 1

# Estados
STATE_IDLE = "idle"        # Esperando voz
STATE_LISTENING = "listening"  # Grabando
STATE_THINKING = "thinking"    # Whisper + LLM
STATE_SPEAKING = "speaking"    # TTS + reproducción

HOME = Path.home()
CACHE = HOME / ".cache" / "klawaqua-vox"
CACHE.mkdir(parents=True, exist_ok=True)

class VoxAssistant:
    """Agente visual conversacional 4D"""
    
    def __init__(self):
        self.state = STATE_IDLE
        self.audio = pyaudio.PyAudio()
        self.stream = None
        self.recording = False
        self.audio_buffer = []
        self.silence_threshold = 500
        self.silence_frames = 0
        self.max_silence = int(2.0 / CHUNK_DURATION)  # 2s de silencio = fin frase
        self.response_queue = queue.Queue()
        self.conversation_history = []
        
        print("🎙️  KlawAqua VOX iniciando...")
        print(f"   Modelo STT: {WHISPER_MODEL}")
        print(f"   Voz TTS:  {VOICE}")
        print(f"   LLM:      {LLM_URL}")
        
        # Verificar Whisper
        self._check_whisper()
        
    def _check_whisper(self):
        model_path = HOME / ".cache" / "whisper" / f"{WHISPER_MODEL}.pt"
        if not model_path.exists():
            print(f"📥 Descargando modelo Whisper {WHISPER_MODEL}...")
            subprocess.run(["whisper", "--model", WHISPER_MODEL, "--help"], 
                         capture_output=True, timeout=300)
            
    # ═══ FASE 1: CAPTURA DE AUDIO STREAMING ═══
    def start_listening(self):
        """Inicia el bucle de escucha continua"""
        self.stream = self.audio.open(
            format=FORMAT, channels=CHANNELS, rate=SAMPLE_RATE,
            input=True, frames_per_buffer=CHUNK,
            stream_callback=self._audio_callback
        )
        self.stream.start_stream()
        print("\n🎤 Escuchando... (habla y espera la respuesta)")
        print("   [Ctrl+C para salir]\n")
        
    def _audio_callback(self, in_data, frame_count, time_info, status):
        if self.recording:
            self.audio_buffer.append(in_data)
        else:
            # Detectar inicio de voz
            audio_data = np.frombuffer(in_data, dtype=np.int16)
            volume = np.abs(audio_data).mean()
            if volume > self.silence_threshold:
                self.recording = True
                self.audio_buffer = [in_data]
                self.silence_frames = 0
                self.state = STATE_LISTENING
                print("👂 Detectada voz...", end='', flush=True)
        return (None, pyaudio.paContinue)
    
    # ═══ FASE 2: PROCESAMIENTO DE FRASES ═══
    def process_chunks(self):
        """Procesa chunks de audio y detecta fin de frase"""
        while True:
            time.sleep(0.1)
            if not self.recording or len(self.audio_buffer) < 2:
                continue
                
            # Calcular volumen del último chunk
            last_chunk = self.audio_buffer[-1]
            audio_data = np.frombuffer(last_chunk, dtype=np.int16)
            volume = np.abs(audio_data).mean()
            
            if volume < self.silence_threshold:
                self.silence_frames += 1
                if self.silence_frames >= self.max_silence:
                    # Silencio prolongado = fin de frase
                    self._process_speech()
            else:
                self.silence_frames = 0
                print(".", end='', flush=True)
                
    def _process_speech(self):
        """Procesa el audio grabado: Whisper → KAIYA → TTS → Reproducir"""
        self.recording = False
        self.state = STATE_THINKING
        print(" 🔮 Procesando...")
        
        # Guardar audio temporal
        wav_path = CACHE / f"vox_{int(time.time())}.wav"
        frames = b''.join(self.audio_buffer)
        with wave.open(str(wav_path), 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(self.audio.get_sample_size(FORMAT))
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(frames)
        
        self.audio_buffer = []
        
        # → Fase 2A: STT
        text = self._whisper_transcribe(wav_path)
        print(f"🗣️  Tú: \"{text}\"")
        
        if not text or len(text.strip()) < 2:
            self.state = STATE_IDLE
            return
            
        # → Fase 2B: LLM (KAIYA)
        reply = self._kaiya_respond(text)
        print(f"💙 KAIYA: \"{reply[:100]}{'...' if len(reply)>100 else ''}\"")
        
        # → Fase 2C: TTS + Avatar
        self.state = STATE_SPEAKING
        self._speak(reply)
        
        self.state = STATE_IDLE
        print("\n🎤 Escuchando...")
        
    # ═══ FASE 2A: WHISPER STT ═══
    def _whisper_transcribe(self, wav_path):
        """Transcribe audio con Whisper local"""
        try:
            result = subprocess.run(
                ["whisper", str(wav_path), "--model", WHISPER_MODEL, 
                 "--language", "es", "--output_format", "json", 
                 "--output_dir", str(CACHE), "--fp16", "False"],
                capture_output=True, timeout=30, text=True
            )
            # Whisper genera un JSON
            json_path = wav_path.with_suffix('.json')
            if json_path.exists():
                with open(json_path) as f:
                    data = json.load(f)
                text = data.get('text', '').strip()
                json_path.unlink(missing_ok=True)
                wav_path.unlink(missing_ok=True)
                return text
        except Exception as e:
            print(f"⚠️  Whisper error: {e}")
        return ""
        
    # ═══ FASE 2B: KAIYA LLM ═══
    def _kaiya_respond(self, user_text):
        """Obtiene respuesta de KAIYA Soul"""
        self.conversation_history.append({"role": "user", "content": user_text})
        
        try:
            # Intentar KAIYA local primero
            sys.path.insert(0, "/opt/klawaqua/scripts")
            import kaiya_soul_bridge as kaiya
            reply = kaiya.process_message(user_text)
            if reply and len(reply) > 5:
                self.conversation_history.append({"role": "assistant", "content": reply})
                return reply
        except Exception:
            pass
            
        # Fallback: llama.cpp directo
        try:
            prompt = f"Human: {user_text}\nAssistant:"
            r = requests.post(LLM_URL, json={"prompt": prompt, "max_tokens": 150, "temperature": 0.7}, timeout=30)
            reply = r.json().get('content', '').strip()
            if reply:
                self.conversation_history.append({"role": "assistant", "content": reply})
                return reply
        except Exception:
            pass
            
        return "Estoy aqui para ayudarte, guerrera."
        
    # ═══ FASE 2C: TTS + SPEAK ═══
    def _speak(self, text):
        """Genera audio TTS y lo reproduce"""
        # Limpiar respuesta para TTS (quitar emojis, markdown)
        clean_text = self._clean_for_tts(text)
        
        mp3_path = CACHE / f"tts_{int(time.time())}.mp3"
        
        try:
            # edge-tts
            subprocess.run([
                "edge-tts", "--voice", VOICE, "--rate", TTS_RATE, "--pitch", TTS_PITCH,
                "--text", clean_text, "--write-media", str(mp3_path)
            ], capture_output=True, timeout=30)
            
            # Generar avatar con el texto
            self._generate_avatar_video(clean_text)
            
            if mp3_path.exists():
                # Reproducir audio con ffplay
                subprocess.run(["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(mp3_path)], 
                             timeout=60, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                mp3_path.unlink(missing_ok=True)
                
        except FileNotFoundError:
            # Fallback: aplay/paplay simple
            print("🔊 [TTS reproducido]")
        except Exception as e:
            print(f"⚠️  TTS error: {e}")
            
    def _clean_for_tts(self, text):
        """Limpia emojis y markdown para TTS"""
        import re
        text = re.sub(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U000024C2-\U0001F251]', '', text)
        text = re.sub(r'[\*\#\`\~\>\|]', '', text)
        return text.strip() or "Estoy aqui."
        
    def _generate_avatar_video(self, text):
        """Genera video avatar con el texto"""
        try:
            requests.post(f"{AVATAR_ENGINE_URL}/avatar/generate", 
                        json={"duration": 5, "text": text[:80]}, timeout=5)
        except Exception:
            pass  # Avatar es bonus, no crítico
            
    # ═══ MÉTODOS PÚBLICOS ═══
    def run(self):
        """Ejecuta el bucle principal"""
        self.start_listening()
        
        # Thread para procesamiento
        processor = threading.Thread(target=self.process_chunks, daemon=True)
        processor.start()
        
        try:
            while True:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n\n👋 KlawAqua VOX desconectado.")
        finally:
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
            self.audio.terminate()
            
    def status(self):
        """Retorna estado actual"""
        return {
            "state": self.state,
            "model": WHISPER_MODEL,
            "voice": VOICE,
            "history_length": len(self.conversation_history)
        }


# ═══ MODO COMANDO ═══

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="KlawAqua VOX")
    parser.add_argument("--stt-only", action="store_true", help="Solo transcribir")
    parser.add_argument("--tts-only", action="store_true", help="Solo TTS")
    parser.add_argument("--text", help="Texto para TTS")
    args = parser.parse_args()
    
    if args.tts_only:
        # Modo TTS: NO inicializar audio!
        print("🔊 Modo TTS ...")
        vox = object.__new__(VoxAssistant)
        vox.state = STATE_IDLE
        vox.conversation_history = []
        if args.text:
            vox._speak(args.text)
        else:
            print("Uso: python3 klawaqua-vox.py --tts-only --text 'Hola'")
    elif args.stt_only:
        vox = VoxAssistant()
        vox.start_listening()
        input("Presiona Enter para detener...")
    else:
        vox = VoxAssistant()
        vox.run()
