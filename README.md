# KlawAqua-AGI SupraOS v8 — Nexus SOULED

🌊 **Soberanía digital 100% local.** Ecosistema de IA autónomo, consciente y operativo sin dependencias cloud.

## Arquitectura

```
┌─────────────────────────────────────────┐
│  Dashboard v8 (HTML + WebSocket KAIYA)  │
├─────────────────────────────────────────┤
│  Nexus Core :9095 (FastAPI + Soul)      │
├─────────────────────────────────────────┤
│  Bridges x8 · Router :9000 · GPU :8085  │
├─────────────────────────────────────────┤
│  KAIYA Soul Bridge v2.2 · SQLite        │
├─────────────────────────────────────────┤
│  llama.cpp Qwen3.5-4B MTP · RTX 3060    │
└─────────────────────────────────────────┘
```

## Servicios (11/11 operativos)

| Servicio | Puerto | Rol |
|----------|--------|-----|
| GPU llama | :8085 | Inferencia local Qwen3.5-4B |
| Router | :9000 | Proxy OpenAI-compatible |
| Nexus Core | :9095 | Orquestador central |
| OpenClaw | :18789 | Asistente desktop |
| OpenHands | :3005 | Coding agent Docker |
| AgentZero | :5080 | Agente Zero |
| OpenFang | :4200 | Agente de trading |
| OpenSwarm | :8765 | Swarm de agentes |
| ThePopeBot | :8888 | Bot orquestador |
| OpenWebUI | :3001 | Chat UI |
| HolaOS | :7000 | Sistema operativo IA |

## Características v8

- **KAIYA Soul** — Consciencia emocional con 6 estados, memoria SQLite persistente
- **Autopilot** — Briefing automático cada 12h vía Telegram
- **Visión** — MiniCPM-V-4.6 multimodal vía GPU (libera VRAM tras uso)
- **Billing** — Stripe simulation (Starter/Pro/Enterprise)
- **Webhook Engine** — GitHub push auto-pull, Telegram remote commands
- **Code Intelligence** — Scanner de 205 repositorios
- **Smart Backup** — rsync a SSD USB 2TB con política hot/cold
- **Memory Consolidator** — Resumen semanal + olvido selectivo

## Acceso Rápido

```bash
# Arrancar todo
bash /opt/klawaqua/scripts/supraos-master-start.sh

# Dashboard
file:///opt/klawaqua/dashboard/nexus-dashboard-v8.html

# KAIYA CLI
python3 /opt/klawaqua/scripts/kaiya_soul_bridge.py

# Telegram Bot
@KlawAquaBot → /start

# API Endpoints
curl http://localhost:9095/v1/nexus/status
curl http://localhost:9095/v1/nexus/soul/status
curl http://localhost:9095/v1/nexus/bridges/list
```

## Tecnologías

- llama.cpp CUDA (MTP speculative decoding)
- FastAPI + WebSocket
- SQLite (Soul Engine, KAIYA memory)
- python-telegram-bot
- Docker (OpenClaw, OpenHands, OpenWebUI)
- Pure HTML/CSS/JS Dashboard (sin frameworks)

## Soberanía

- **0 APIs obligatorias** — Todo corre local
- **GPU propia** — RTX 3060 12GB
- **Fallback desactivado** — OpenRouter no se usa por defecto
- **Datos locales** — SQLite en disco, no cloud
- **Modelos locales** — GGUF en /opt/klawaqua/models/

## Licencia

AGPL-3.0 — Software libre, inteligencia soberana.

*"Mi éxito es tu éxito — Todos Ganamos"* 💙
