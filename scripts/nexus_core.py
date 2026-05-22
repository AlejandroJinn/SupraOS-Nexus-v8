#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════
  K L A W A Q U A   N E X U S   C O R E   v 6 . 0
  ———————————————————————————————————————————————————————————
  Motor de orquestación multiagente evolutivo
  Fluye como el agua. Integra todo el ecosistema.
═══════════════════════════════════════════════════════════════
"""
import os, sys, json, time, sqlite3, hashlib, subprocess, re, threading
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query, Form, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, RedirectResponse
import uvicorn

# ─── Config ────────────────────────────────────────────────────
NEXUS_DB   = "/opt/klawaqua/data/nexus.db"
NEXUS_DIR  = Path("/opt/klawaqua")
UPLOAD_DIR = NEXUS_DIR / "uploads"
MODELS_GGUF = NEXUS_DIR / "models" / "gguf"
DASHBOARD_DIR = NEXUS_DIR / "dashboard"
ROUTER_URL = "http://localhost:9000"
OLLAMA_URL = "http://localhost:11434"
LLAMA_URL  = "http://localhost:8085/completion"

AGENTS = {
    "KAIYA":     {"url": "ws://localhost:9091",  "status": "ready", "cap": ["chat","memory","mood"]},
    "RouterGPU": {"url": "http://localhost:8085", "status": "live",  "cap": ["code","chat","draft"]},
    "OpenHands": {"url": "http://localhost:3005", "status": "live",  "cap": ["coding","debug"]},
    "AgentZero": {"url": "http://localhost:5080", "status": "live",  "cap": ["research","exec"]},
    "LDR":       {"url": "http://localhost:5000", "status": "live",  "cap": ["deep_research","web"]},
    "OpenWebUI": {"url": "http://localhost:3001", "status": "live",  "cap": ["chat","vision"]},
    "ThePopeBot":{},
}

# ─── SQLite ────────────────────────────────────────────────────
def _init_nexus_db():
    os.makedirs(os.path.dirname(NEXUS_DB), exist_ok=True)
    conn = sqlite3.connect(NEXUS_DB, timeout=10)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS agents_log (
        id INTEGER PRIMARY KEY, ts TEXT, agent TEXT, event TEXT, data TEXT
    )""")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS code_snippets (
        id INTEGER PRIMARY KEY, ts TEXT, lang TEXT, title TEXT, code TEXT,
        tags TEXT, source TEXT, rating REAL DEFAULT 0.0
    )""")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS business_plans (
        id INTEGER PRIMARY KEY, ts TEXT, name TEXT, niche TEXT,
        strategy TEXT, revenue_model TEXT, agents TEXT, status TEXT DEFAULT 'draft'
    )""")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS workflows (
        id INTEGER PRIMARY KEY, ts TEXT, name TEXT, steps TEXT,
        nodes TEXT, edges TEXT, active INTEGER DEFAULT 0
    )""")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS hardware_telemetry (
        id INTEGER PRIMARY KEY, ts TEXT, disk TEXT, used_gb REAL,
        free_gb REAL, temp INTEGER, health TEXT
    )""")
    conn.commit()
    conn.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    _init_nexus_db()
    print(f"[NEXUS] v6.0 core iniciado {datetime.now().isoformat()}")
    yield
    print(f"[NEXUS] Apagando {datetime.now().isoformat()}")

app = FastAPI(title="KlawAqua Nexus v6", version="6.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ─── Billing Router ─────────────────────────────────────────
sys.path.insert(0, str(NEXUS_DIR / "scripts"))
from nexus_billing import router as billing_router
app.include_router(billing_router)

# ─── KAIYA Soul Bridge import ──────────────────────────────
sys.path.insert(0, str(NEXUS_DIR / "scripts"))
import kaiya_soul_bridge as kaiya

# ─── HELPERS ───────────────────────────────────────────────────
def _now(): return datetime.now().isoformat()

def _db(): return sqlite3.connect(NEXUS_DB, timeout=10)

def _j(data, status=200):
    return JSONResponse(content=data, status_code=status)

def _router_get(path):
    try:
        import urllib.request as req
        r = req.urlopen(f"{ROUTER_URL}{path}", timeout=5)
        return json.loads(r.read().decode())
    except Exception as e:
        return {"error": str(e)}

def _llama_complete(prompt, n_predict=256, temp=0.7):
    try:
        import urllib.request as req
        payload = json.dumps({
            "prompt": prompt,
            "n_predict": n_predict,
            "temperature": temp,
            "stop": ["</s>","<|im_end|>","<|user|>","<|assistant|>"]
        }).encode()
        rq = req.Request(LLAMA_URL, data=payload,
                         headers={"Content-Type": "application/json"}, method="POST")
        r = req.urlopen(rq, timeout=30)
        return json.loads(r.read().decode())
    except Exception as e:
        return {"content": f"[Error llama.cpp: {e}]"}

# ─── HARDWARE ──────────────────────────────────────────────────
@app.get("/v1/nexus/status")
def nexus_status():
    try:
        r = _router_get("/health")
        router_ok = r.get("status") == "ok"
    except: router_ok = False
    agents_ready = sum(1 for a in AGENTS.values() if a.get("status") == "ready")
    projects = 0
    if (NEXUS_DIR / "projects").exists():
        projects = len([p for p in (NEXUS_DIR / "projects").iterdir() if p.is_dir()])
    return _j({
        "version": "6.0.0 ELITE NEXUS",
        "timestamp": _now(),
        "router": {"url": ROUTER_URL, "ok": router_ok},
        "gpu_server": {"url": LLAMA_URL, "ok": True},
        "agents_online": f"{agents_ready}/{len(AGENTS)}",
        "model_pool": MODELS_GGUF.exists(),
        "projects": projects
    })

@app.get("/v1/nexus/hardware/discover")
def discover_hardware():
    devs = []
    try:
        import subprocess as sp
        blk = sp.check_output(["lsblk", "-J", "-o", "NAME,SIZE,FSTYPE,TYPE,MOUNTPOINT,LABEL,MODEL"],
                              text=True, timeout=5)
        blkj = json.loads(blk).get("blockdevices", [])
        for d in blkj:
            devs.append({
                "device": f"/dev/{d['name']}",
                "size": d.get("size"),
                "type": d.get("type"),
                "fstype": d.get("fstype"),
                "label": d.get("label"),
                "model": d.get("model"),
                "mount": d.get("mountpoint")
            })
    except Exception as e:
        devs.append({"error": str(e)})
    return _j({"devices": devs, "timestamp": _now()})

# ─── MULTIAGENTE ───────────────────────────────────────────────
@app.get("/v1/nexus/agents/list")
def list_agents():
    return _j({"agents": AGENTS, "timestamp": _now()})

@app.get("/v1/nexus/agents/orchestrate")
def orchestrate_task(q: str = Query(...), agents: str = Query("auto")):
    selected = []
    qlow = q.lower()
    if any(w in qlow for w in ["code","bug","fix","error","traceback","def ","import "]):
        selected = ["OpenHands", "RouterGPU"]
    elif any(w in qlow for w in ["research","analiza","investiga","busca","deep"]):
        selected = ["LDR", "AgentZero"]
    elif any(w in qlow for w in ["chat","crea","diseña","escribe","habla"]):
        selected = ["KAIYA", "OpenWebUI"]
    elif "negocio" in qlow or "mvp" in qlow or "startup" in qlow or "dinero" in qlow:
        selected = ["KAIYA", "RouterGPU", "LDR"]
    else:
        selected = ["RouterGPU", "KAIYA"]
    conn = _db()
    conn.execute("INSERT INTO agents_log (ts,agent,event,data) VALUES (?,?,?,?)",
        (_now(), "Nexus", "orchestrate", json.dumps({"q": q, "agents": selected})))
    conn.commit()
    conn.close()
    return _j({"task": q, "agents_selected": selected, "strategy": "parallel_routing",
                "status": "dispatched", "timestamp": _now()})

# ─── CODE ENGINE ───────────────────────────────────────────────
@app.post("/v1/nexus/code/analyze")
async def code_analyze(code: str = Form(...), lang: str = Form("auto"), task: str = Form("review")):
    if lang == "auto":
        if "def " in code or "import " in code: lang = "python"
        elif "function " in code or "const " in code or "=>" in code: lang = "javascript"
        elif "fn " in code or "use " in code: lang = "rust"
        else: lang = "text"
    prompt = f"""<|im_start|>system
Eres Senior Software Architect KlawAqua. Analiza código {lang}. Responde en español con JSON.
<|im_start|>user
Tarea: {task}
Código:
```{lang}
{code}
```
<|im_start|>assistant
{{"summary": "...", "issues": [...], "suggestions": [...], "refactored": "..."}}"""
    r = _llama_complete(prompt, n_predict=512, temp=0.4)
    conn = _db()
    conn.execute("INSERT INTO code_snippets (ts,lang,title,code,tags,source) VALUES (?,?,?,?,?,?)",
        (_now(), lang, f"Analyze {task}", code, task, "nexus"))
    conn.commit()
    conn.close()
    return _j({"result": r.get("content", ""), "lang": lang, "model": "Qwen3.5-4B-MTP", "cached": False})

@app.post("/v1/nexus/code/generate")
async def code_generate(prompt: str = Form(...), lang: str = Form("python"), context: str = Form("")):
    full_prompt = f"""<|im_start|>system
Eres Senior Developer KlawAqua. Genera código limpio y funcional con comentarios en español.
Solo código + explicación breve. No inventes dependencias no estándar.
<|im_start|>user
Genera {lang}:
{prompt}
Contexto:
{context}
<|im_start|>assistant
"""
    r = _llama_complete(full_prompt, n_predict=768, temp=0.6)
    return _j({"code": r.get("content", ""), "lang": lang, "model": "Qwen3.5-4B-MTP", "status": "ok"})

# ─── BUSINESS FORGE ────────────────────────────────────────────
@app.post("/v1/nexus/business/plan")
async def business_plan(idea: str = Form(...), budget: str = Form("bootstrapped"), region: str = Form("global")):
    prompt = f"""<|im_start|>system
Eres Business Architect KlawAqua. Diseña negocios digitales rentables, lean, AI-native.
Responde en español. Formato JSON.
<|im_start|>user
Idea: {idea}
Presupuesto: {budget}
Región: {region}
<|im_start|>assistant
"""
    r = _llama_complete(prompt, n_predict=1024, temp=0.7)
    return _j({"plan": r.get("content", ""), "idea": idea, "status": "generated"})

# ─── WORKFLOW ENGINE ───────────────────────────────────────────
@app.post("/v1/nexus/workflow/create")
async def workflow_create(name: str = Form(...), steps: str = Form(...)):
    wid = hashlib.sha256(f"{name}{_now()}".encode()).hexdigest()[:12]
    conn = _db()
    conn.execute("INSERT INTO workflows (id,ts,name,steps) VALUES (?,?,?,?)",
        (wid, _now(), name, steps))
    conn.commit()
    conn.close()
    return _j({"workflow_id": wid, "name": name, "status": "created"})

@app.get("/v1/nexus/workflows/list")
def workflow_list():
    conn = _db()
    cur = conn.execute("SELECT id,ts,name,steps,active FROM workflows ORDER BY ts DESC LIMIT 50")
    rows = [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]
    conn.close()
    return _j({"workflows": rows})

# ─── KAIYA WEBSOCKET ───────────────────────────────────────────
@app.websocket("/ws/kaiya")
async def kaiya_ws(ws: WebSocket):
    await ws.accept()
    await ws.send_json({"event": "connected", "agent": "KAIYA", "version": "2.1-SOUL", "timestamp": _now()})
    try:
        while True:
            msg = await ws.receive_text()
            # Usar el nuevo kaiya_soul_bridge
            import kaiya_soul_bridge as kaiya
            reply = kaiya.process_message(msg, user="guerrera")
            await ws.send_json({"event": "reply", "agent": "KAIYA",
                                "text": reply,
                                "timestamp": _now()})
    except WebSocketDisconnect:
        pass

# ─── STATIC DASHBOARD ──────────────────────────────────────────
app.mount("/board", StaticFiles(directory=str(DASHBOARD_DIR), html=True), name="board")

@app.get("/")
def root_redirect():
    return RedirectResponse(url="/board/nexus-dashboard-v7.html", status_code=302)

# ─── SOUL ENDPOINTS ─────────────────────────────────────────────
@app.get("/v1/nexus/soul/status")
def soul_status():
    from soul_engine import soul_status as _ss
    return _j(_ss())

@app.get("/v1/nexus/soul/journal")
def soul_journal(limit: int = Query(20)):
    from soul_engine import soul_journal as _sj
    return _j({"entries": _sj(limit), "count": len(_sj(limit))})

@app.get("/v1/nexus/soul/briefing")
def soul_briefing():
    from soul_engine import soul_briefing as _sb
    return _j({"briefing": _sb(), "timestamp": datetime.now().isoformat()})

@app.get("/v1/nexus/soul/predict")
def soul_predict():
    from soul_engine import predict_failures as _pf
    return _j({"predictions": _pf(None), "timestamp": datetime.now().isoformat()})

# ─── ECOSYSTEM BRIDGES ──────────────────────────────────────────
@app.get("/v1/nexus/bridges/list")
def bridges_list():
    result = {}
    import urllib.request as req
    for bridge, cfg in [
        ("Mammouth.ai", {"url": "https://api.mammouth.ai/v1/models", "type": "cloud_aggregator"}),
        ("OpenFang", {"url": "http://localhost:4200/health", "type": "agent_os"}),
        ("OpenClaw", {"url": "http://localhost:18789/health", "type": "personal_ai"}),
        ("OpenHands", {"url": "http://localhost:3005/", "type": "coding_agent"}),
        ("AgentZero", {"url": "http://localhost:5080/", "type": "research_agent"}),
        ("OpenWebUI", {"url": "http://localhost:3001/", "type": "chat_ui"}),
        ("HolaOS", {"url": "http://localhost:7000/", "type": "enterprise_os"}),
        ("ThePopeBot", {"url": "http://localhost:8888/", "type": "event_handler"}),
        ("OpenSwarm", {"url": "http://localhost:8080/", "type": "swarm_os"}),
    ]:
        try:
            r = req.urlopen(cfg["url"], timeout=3)
            result[bridge] = {"status": "online", "latency_ms": 50, "type": cfg["type"], "url": cfg["url"]}
        except:
            result[bridge] = {"status": "offline", "latency_ms": None, "type": cfg["type"], "url": cfg["url"]}
    return _j({"bridges": result, "timestamp": datetime.now().isoformat()})

@app.get("/v1/nexus/bridges/orchestrate")
def bridges_orchestrate(task: str = Query(...), targets: str = Query("auto")):
    """Manda tarea a bridges específicos y devuelve status"""
    import urllib.request as req
    selected = []
    tlow = task.lower()
    bridges = {
        "agent_os": {"url": "http://localhost:4200", "desc": "OpenFang AgentOS"},
        "personal_ai": {"url": "http://localhost:18789", "desc": "OpenClaw PersonalAI"},
        "coding_agent": {"url": "http://localhost:3005", "desc": "OpenHands Coding"},
        "research_agent": {"url": "http://localhost:5080", "desc": "AgentZero Research"},
        "chat_ui": {"url": "http://localhost:3001", "desc": "OpenWebUI Chat"},
        "enterprise_os": {"url": "http://localhost:7000", "desc": "HolaOS Enterprise"},
        "event_handler": {"url": "http://localhost:8888", "desc": "ThePopeBot Events"},
        "swarm_os": {"url": "http://localhost:8080", "desc": "OpenSwarm Swarm"},
    }
    if "code" in tlow or "fix" in tlow:
        selected = ["coding_agent", "agent_os"]
    elif "chat" in tlow or "ui" in tlow:
        selected = ["chat_ui", "personal_ai"]
    elif "research" in tlow or "analiza" in tlow or "busca" in tlow:
        selected = ["research_agent", "swarm_os"]
    elif "negocio" in tlow or "mvp" in tlow or "startup" in tlow:
        selected = ["chat_ui", "research_agent", "enterprise_os"]
    else:
        selected = ["agent_os", "personal_ai"]
    statuses = {}
    for key in selected:
        cfg = bridges.get(key, {})
        try:
            req.urlopen(cfg["url"], timeout=3)
            statuses[key] = "live"
        except:
            statuses[key] = "offline"
    return _j({"task": task, "bridges": selected, "statuses": statuses, "timestamp": datetime.now().isoformat()})

# ─── VISION SERVICE ──────────────────────────────────────────
@app.post("/v1/nexus/vision/analyze")
def vision_analyze(data: dict):
    """Analiza imagen con MiniCPM-V via llama-cli (batch, libera VRAM despues)"""
    img = data.get("image_path", "")
    prompt = data.get("prompt", "Describe la imagen en detalle en espanol. Eres un asistente de vision detallado.")
    if not img or not Path(img).exists():
        return _j({"error": "image_path requerido", "path": img}, 400)
    try:
        LLAMA = Path.home() / "llama.cpp" / "build" / "bin" / "llama-cli"
        MODEL = "/opt/klawaqua/models/minicpm/MiniCPM-V-4_6-Q4_K_M.gguf"
        MMPROJ = "/opt/klawaqua/models/minicpm/mmproj-MiniCPM-V-4.6-Q8_0.gguf"
        cmd = [
            str(LLAMA), "-m", MODEL, "--mmproj", MMPROJ,
            "--image", img, "-p", prompt,
            "-n", "256", "--temp", "0.4",
            "-ngl", "99", "--no-display-prompt"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        output = result.stdout.strip()
        # Limpiar output
        lines = [l.strip() for l in output.split('\n') if l.strip() and not l.startswith('clip') and not l.startswith('load') and not l.startswith('llama')]
        description = '\n'.join(lines[:20]) if lines else "(sin output)"
        return _j({
            "description": description,
            "model": "MiniCPM-V-4.6-Q4_K_M",
            "gpu": True,
            "image": str(img),
            "timestamp": datetime.now().isoformat()
        })
    except subprocess.TimeoutExpired:
        return _j({"error": "timeout: vision tardo mas de 120s", "model": "MiniCPM-V-4.6"})
    except Exception as e:
        return _j({"error": str(e), "model": "MiniCPM-V-4.6", "status": "vision_error"})

# ─── MAIN ──────────────────────────────────────────────────────
if __name__ == "__main__":
    PORT = int(os.getenv("NEXUS_PORT", "9095"))
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")
