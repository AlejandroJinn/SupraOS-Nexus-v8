#!/usr/bin/env python3
"""
KlawAqua Telegram Bot — Conectado a Nexus v7 SOULED
Reenvia comandos al ecosistema y responde via KAIYA Soul
"""
import os, sys, json, subprocess, urllib.request as req

# Instalar python-telegram-bot si no existe
try:
    import telegram
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "python-telegram-bot", "-q"])
    import telegram

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8469591478:AAGjPrpL5XR7Igh0fqp-JeL6Tma8NMEDEy8")
NEXUS_URL = "http://localhost:9095"

def nexus_api(path, method="GET", data=None):
    try:
        url = f"{NEXUS_URL}{path}"
        if method == "GET":
            r = req.urlopen(url, timeout=10)
        else:
            body = json.dumps(data).encode() if data else None
            rq = req.Request(url, body, headers={"Content-Type":"application/json"}, method=method)
            r = req.urlopen(rq, timeout=10)
        return json.loads(r.read().decode())
    except Exception as e:
        return {"error": str(e)}

# --- Handlers ---
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    username = update.effective_user.username or "desconocido"
    # Registrar chat_id en autopilot DB
    try:
        sys.path.insert(0, "/opt/klawaqua/scripts")
        import autopilot_daemon as ap
        ap.register_chat(str(chat_id), username)
    except Exception as e:
        print(f"[Telegram] No pude registrar chat_id: {e}")
    
    await update.message.reply_text(
        "KlawAqua Nexus v7 - Guerrera, tu flujo continua aqui.\n\n"
        "Comandos:\n/status - Estado del sistema\n/bridges - Puentes activos\n"
        "/soul - Alma del sistema\n/chat mensaje - Hablar con KAIYA\n\n"
        f"Tu chat_id: `{chat_id}`",
        parse_mode="Markdown"
    )

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = nexus_api("/v1/nexus/status")
    if "error" in s:
        await update.message.reply_text(f"Error: {s['error']}"); return
    txt = (f"Nexus v7 OK\nRouter: {'OK' if s['router']['ok'] else 'ERR'}\n"
           f"GPU: {'OK' if s['gpu_server']['ok'] else 'ERR'}\n"
           f"Model Pool: {'OK' if s['model_pool'] else 'ERR'}\nProyectos: {s['projects']}")
    await update.message.reply_text(txt)

async def cmd_bridges(update: Update, context: ContextTypes.DEFAULT_TYPE):
    b = nexus_api("/v1/nexus/bridges/list")
    bridges = b.get("bridges", {})
    lines = [f"{'OK' if v['status']=='online' else 'OFF'} {k}" for k,v in bridges.items()]
    await update.message.reply_text("Puentes:\n" + "\n".join(lines))

async def cmd_soul(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = nexus_api("/v1/nexus/soul/status")
    txt = (f"Alma del Sistema\nEnergia: {s['energy']*100:.0f}%\n"
           f"Valentia: {s['valence']*100:.0f}%\nEstrés: {s['stress']*100:.0f}%\n"
           f"Curiosidad: {s['curiosity']*100:.0f}%\nAmor: {s['love']*100:.0f}%")
    await update.message.reply_text(txt)

async def cmd_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usa: /chat hola KAIYA"); return
    msg = " ".join(context.args)
    try:
        sys.path.insert(0, "/opt/klawaqua/scripts")
        import kaiya_soul_bridge as kaiya
        reply = kaiya.process_message(msg)
        await update.message.reply_text(reply)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def cmd_vision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Analiza imagen subida al chat"""
    try:
        if update.message.photo:
            # Descargar foto
            photo = update.message.photo[-1]
            file = await context.bot.get_file(photo.file_id)
            tmp_path = f"/tmp/vision_{photo.file_id}.jpg"
            await file.download_to_drive(tmp_path)
            
            # Llamar a visión
            import urllib.request as req
            body = json.dumps({"image_path": tmp_path, "prompt": "Describe la imagen detalladamente en español"}).encode()
            r = req.Request("http://localhost:9095/v1/nexus/vision/analyze", body, headers={"Content-Type": "application/json"})
            resp = req.urlopen(r, timeout=120)
            d = json.loads(resp.read())
            
            if "error" in d:
                await update.message.reply_text(f"Vision error: {d['error']}")
            else:
                await update.message.reply_text(f"👁️ *Vision KAIYA:*\n{d.get('description', '(sin descripcion)')[:400]}", parse_mode="Markdown")
        else:
            await update.message.reply_text("Envia una imagen con /vision para analizarla")
    except Exception as e:
        await update.message.reply_text(f"Error vision: {e}")

async def msg_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text.startswith('/'): return
    try:
        sys.path.insert(0, "/opt/klawaqua/scripts")
        import kaiya_soul_bridge as kaiya
        reply = kaiya.process_message(text)
        await update.message.reply_text(reply)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

# --- Main ---
if __name__ == "__main__":
    print(f"[Telegram Bot] Iniciando...")
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("bridges", cmd_bridges))
    app.add_handler(CommandHandler("soul", cmd_soul))
    app.add_handler(CommandHandler("chat", cmd_chat))
    app.add_handler(CommandHandler("vision", cmd_vision))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, msg_handler))
    print("[Telegram Bot] Corriendo...")
    app.run_polling(stop_signals=[])
