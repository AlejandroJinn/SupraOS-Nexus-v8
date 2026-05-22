#!/usr/bin/env python3
"""ThePopeBot - Supremo Orquestador KlawAqua
Servicio HTTP en puerto 8080 que enruta solicitudes a los agentes del ecosistema.
Sin bot de Telegram, solo orquestación local.
"""

import json
import subprocess
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

PORT = 8888

AGENTS = {
    "agent_zero": {"url": "http://localhost:5080", "description": "Investigación y análisis"},
    "openhands": {"url": "http://localhost:3000", "description": "Desarrollo de código"},
    "openclaw": {"url": "http://localhost:18789", "description": "Asistente general"},
    "ollama": {"url": "http://localhost:11434", "description": "Modelos locales"},
    "litellm": {"url": "http://localhost:4000", "description": "Proxy de modelos"},
}


def check_agent_health(name, agent):
    try:
        if name == "ollama":
            req = urllib.request.Request(f"{agent['url']}/")
        elif name == "agent_zero":
            req = urllib.request.Request(f"{agent['url']}/api/health")
        else:
            req = urllib.request.Request(agent["url"])
        req.method = "GET"
        resp = urllib.request.urlopen(req, timeout=3)
        return resp.status == 200
    except Exception:
        return False


def get_agent_status():
    status = {}
    for name, agent in AGENTS.items():
        status[name] = {
            "available": check_agent_health(name, agent),
            "description": agent["description"],
        }
    return status


def chat_with_ollama(prompt, model="qwen3.5:4b"):
    data = json.dumps(
        {"model": model, "prompt": prompt, "stream": False}
    ).encode()
    req = urllib.request.Request(
        "http://localhost:11434/api/generate", data=data, headers={"Content-Type": "application/json"}
    )
    resp = urllib.request.urlopen(req, timeout=120)
    result = json.loads(resp.read())
    return result.get("response", "")


class PopebotHandler(BaseHTTPRequestHandler):
    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2, ensure_ascii=False).encode())

    def do_GET(self):
        if self.path == "/" or self.path == "/health":
            self._send_json({
                "name": "ThePopeBot",
                "role": "Supreme Orchestrator",
                "status": "online",
                "agents": get_agent_status(),
                "routing": {
                    "investigacion": "agent_zero",
                    "codigo": "openhands",
                    "general": "ollama_local",
                    "asistente": "openclaw",
                },
                "timestamp": datetime.now().isoformat(),
            })
        elif self.path == "/agents":
            self._send_json(get_agent_status())
        else:
            self._send_json({"error": "Not found"}, 404)

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode()
        try:
            request = json.loads(body)
        except json.JSONDecodeError:
            self._send_json({"error": "Invalid JSON"}, 400)
            return

        task_type = request.get("type", request.get("task", "general"))
        prompt = request.get("prompt", request.get("query", request.get("message", "")))
        model = request.get("model", "qwen3.5:4b")

        # Routing logic
        routing_map = {
            "investigacion": "agent_zero",
            "research": "agent_zero",
            "codigo": "openhands",
            "code": "openhands",
            "desarrollo": "openhands",
            "general": "ollama",
            "chat": "ollama",
            "asistente": "openclaw",
            "assistant": "openclaw",
            "litellm": "litellm",
        }
        target = routing_map.get(task_type.lower(), "ollama")

        response = {
            "orchestrator": "ThePopeBot",
            "task_type": task_type,
            "target_agent": target,
            "model": model,
        }

        # Execute based on target
        if target == "ollama":
            try:
                response["result"] = chat_with_ollama(prompt, model)
                response["status"] = "success"
            except Exception as e:
                response["status"] = "error"
                response["error"] = str(e)
        elif target == "agent_zero":
            response["status"] = "routed"
            response["message"] = f"Task delegated to Agent Zero at {AGENTS['agent_zero']['url']}"
            response["note"] = "Use Agent Zero API directly for agent tasks"
        elif target == "openhands":
            response["status"] = "routed"
            response["message"] = f"Task delegated to OpenHands at {AGENTS['openhands']['url']}"
            response["note"] = "Use OpenHands API/UI directly for coding tasks"
        elif target == "openclaw":
            response["status"] = "routed"
            response["message"] = f"Task delegated to OpenCLAW at {AGENTS['openclaw']['url']}"
        elif target == "litellm":
            response["status"] = "routed"
            response["message"] = f"Task delegated to LiteLLM at {AGENTS['litellm']['url']}"
        else:
            response["status"] = "unknown_target"

        self._send_json(response)


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), PopebotHandler)
    print(f"ThePopeBot Orchestrator listening on port {PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
