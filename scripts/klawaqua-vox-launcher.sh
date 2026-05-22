#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# KlawAqua VOX Launcher — Asistente conversacional visual 4D
# ═══════════════════════════════════════════════════════════════

echo "🎙️  KlawAqua VOX — Iniciando..."
echo "   Presiona Ctrl+C para detener"
echo ""

# Verificar dependencias
for cmd in python3 whisper edge-tts ffplay; do
    if ! command -v $cmd &> /dev/null; then
        echo "❌ Falta: $cmd"
        exit 1
    fi
done

# Asegurar servicios base
if ! curl -s http://localhost:8085/completion > /dev/null 2>&1; then
    echo "⚠️  GPU :8085 no responde. Intentando arrancar..."
    # Intentar arrancar llama-server
fi

if ! curl -s http://localhost:8600/health > /dev/null 2>&1; then
    echo "⚠️  Avatar Engine :8600 no responde."
fi

cd /opt/klawaqua/scripts
python3 klawaqua-vox.py "$@"
