#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════╗
║        KLAWAQUA-AGI — ELITE ORCHESTRATOR v4.1            ║
║   Fast Router · Economy · No Hangs                       ║
╚══════════════════════════════════════════════════════════╝
"""

import os, sys, json, time, sqlite3, hashlib, base64, re, subprocess, socket, threading
from datetime import datetime, timedelta
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs
import urllib.request, urllib.error
from collections import defaultdict
import thread_memory  # Persistent thread context
import router_auth     # API keys, auth, rate limiting
import router_billing   # Stripe billing

KLAWAQUA = "/opt/klawaqua"
PORT = 9000
LOG_DIR = f"{KLAWAQUA}/logs"
UPLOAD_DIR = f"{KLAWAQUA}/uploads"
AUDIO_DIR = f"{KLAWAQUA}/uploads/audio"
Path(LOG_DIR).mkdir(exist_ok=True)
Path(UPLOAD_DIR).mkdir(exist_ok=True)
Path(AUDIO_DIR).mkdir(exist_ok=True)
ROUTER_DB = f"{KLAWAQUA}/data/router_memory.db"
MODEL_POOL_DB = f"{KLAWAQUA}/data/model_pool.db"
ECONOMY_DB = f"{KLAWAQUA}/data/economy.db"
Path(f"{KLAWAQUA}/data").mkdir(exist_ok=True)
CONFIG_FILE = f"{KLAWAQUA}/config/api_keys.json"
Path(f"{KLAWAQUA}/config").mkdir(exist_ok=True)

# ── Config ──────────────────────────────────────────────────
def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f: return json.load(f)
        except: pass
    return {
        "openrouter_api_key": os.environ.get("OPENROUTER_API_KEY",""),
        "openai_api_key": os.environ.get("OPENAI_API_KEY",""),
        "anthropic_api_key": os.environ.get("ANTHROPIC_API_KEY",""),
        "moonshot_api_key": os.environ.get("MOONSHOT_API_KEY",""),
        "minimax_api_key": os.environ.get("MINIMAX_API_KEY",""),
        "cloud_enabled": False,
        "auto_mode": True,
        "economy_enabled": True,
        "daily_budget_usd": 10.0,
        "monthly_budget_usd": 100.0,
        "auto_economize_threshold": 0.7,
        "prefer_local_threshold": 0.3,
    }

def save_config(cfg):
    with open(CONFIG_FILE, "w") as f: json.dump(cfg, f, indent=2)

config = load_config()

# ── Logging ────────────────────────────────────────────────
def log(msg, level="INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {level}: {msg}"
    print(line, flush=True)
    try:
        with open(f"{LOG_DIR}/router.log","a") as f: f.write(line+"\n")
    except: pass

# ═══════════════════════════════════════════════════════════
# SECTION 1: MODEL POOL DATABASE (ECONOMY)
# ═══════════════════════════════════════════════════════════

MODEL_POOL_SCHEMA = """
CREATE TABLE IF NOT EXISTS model_pool (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id TEXT UNIQUE NOT NULL,
    provider TEXT NOT NULL,
    name TEXT NOT NULL,
    context_window INTEGER DEFAULT 4096,
    input_cost_per_1m REAL DEFAULT 0,
    output_cost_per_1m REAL DEFAULT 0,
    avg_latency_ms REAL DEFAULT 0,
    success_rate REAL DEFAULT 1.0,
    request_count INTEGER DEFAULT 0,
    total_cost_usd REAL DEFAULT 0,
    is_local INTEGER DEFAULT 1,
    is_active INTEGER DEFAULT 1,
    last_used TEXT,
    tags TEXT DEFAULT '',
    min_free_ram_mb INTEGER DEFAULT 2048,
    max_concurrent INTEGER DEFAULT 3,
    current_concurrent INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS model_capabilities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id TEXT NOT NULL,
    capability TEXT NOT NULL,
    score REAL DEFAULT 0.5,
    FOREIGN KEY (model_id) REFERENCES model_pool(model_id)
);
CREATE TABLE IF NOT EXISTS model_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alias TEXT UNIQUE NOT NULL,
    model_id TEXT NOT NULL,
    FOREIGN KEY (model_id) REFERENCES model_pool(model_id)
);
CREATE INDEX IF NOT EXISTS idx_model_provider ON model_pool(provider);
CREATE INDEX IF NOT EXISTS idx_cap_model ON model_capabilities(model_id);
"""

def _init_model_pool():
    conn = sqlite3.connect(MODEL_POOL_DB)
    conn.executescript(MODEL_POOL_SCHEMA)
    conn.commit()
    # Seed models if empty
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM model_pool")
    if cur.fetchone()[0] == 0:
        models = [
            ("qwen3:4b","ollama","Qwen3 4B","local,fast,reasoning",1,0.0,0.0),
            ("qwen2.5-coder:1.5b","ollama","Qwen2.5 Coder 1.5B","local,coding",1,0.0,0.0),
            ("deepseek-r1:1.5b","ollama","DeepSeek R1 1.5B","local,reasoning",1,0.0,0.0),
            ("granite3.2:2b","ollama","Granite 3.2 2B","local,coding,reasoning",1,0.0,0.0),
            ("all-minilm:latest","ollama","All-MiniLM","local,embedding",1,0.0,0.0),
            ("nomic-embed-text:latest","ollama","Nomic Embed","local,embedding",1,0.0,0.0),
            ("anthropic/claude-sonnet-4","openrouter","Claude Sonnet 4","cloud,reasoning",0,0.003,0.015),
            ("openai/gpt-4o-mini","openrouter","GPT-4o Mini","cloud,fast",0,0.00015,0.0006),
            ("deepseek-ai/deepseek-r1","openrouter","DeepSeek R1","cloud,reasoning",0,0.0014,0.0022),
            ("google/gemini-2.0-flash","openrouter","Gemini 2.0 Flash","cloud,fast",0,0.0,0.0),
            ("nvidia/llama-3.1-nemotron-70b","openrouter","Nemotron 70B","cloud,reasoning",0,0.0005,0.0008),
            ("meta-llama/llama-3.3-70b","openrouter","LLaMA 3.3 70B","cloud,coding",0,0.00088,0.00088),
        ]
        cur.executemany("INSERT INTO model_pool (model_id,provider,name,tags,is_local,input_cost_per_1m,output_cost_per_1m) VALUES (?,?,?,?,?,?,?)", models)
        # Seed capabilities
        caps = [
            ("qwen3:4b","general",0.7),("qwen3:4b","reasoning",0.8),("qwen3:4b","coding",0.6),
            ("qwen2.5-coder:1.5b","general",0.6),("qwen2.5-coder:1.5b","coding",0.8),
            ("deepseek-r1:1.5b","reasoning",0.85),("deepseek-r1:1.5b","general",0.5),
            ("granite3.2:2b","coding",0.75),("granite3.2:2b","reasoning",0.65),
            ("all-minilm:latest","embedding",0.9),
            ("nomic-embed-text:latest","embedding",0.9),
            ("anthropic/claude-sonnet-4","reasoning",0.95),("anthropic/claude-sonnet-4","coding",0.9),
            ("openai/gpt-4o-mini","fast",0.9),("openai/gpt-4o-mini","general",0.85),
            ("deepseek-ai/deepseek-r1","reasoning",0.95),
            ("google/gemini-2.0-flash","fast",0.9),("google/gemini-2.0-flash","general",0.85),
            ("nvidia/llama-3.1-nemotron-70b","reasoning",0.9),("nvidia/llama-3.1-nemotron-70b","coding",0.85),
            ("meta-llama/llama-3.3-70b","coding",0.85),("meta-llama/llama-3.3-70b","general",0.8),
        ]
        cur.executemany("INSERT INTO model_capabilities (model_id,capability,score) VALUES (?,?,?)", caps)
        conn.commit()
    conn.close()

_init_model_pool()

# ── Economy DB ─────────────────────────────────────────────
ECONOMY_SCHEMA = """
CREATE TABLE IF NOT EXISTS economy_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    total_requests INTEGER DEFAULT 0,
    local_requests INTEGER DEFAULT 0,
    cloud_requests INTEGER DEFAULT 0,
    total_cost_usd REAL DEFAULT 0,
    avg_latency_ms REAL DEFAULT 0,
    savings_usd REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS request_costs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    model_id TEXT,
    source TEXT,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    latency_ms INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0,
    success INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS budget_periods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL,
    budget_usd REAL DEFAULT 0,
    spent_usd REAL DEFAULT 0,
    requests INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS economy_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    event_type TEXT,
    details TEXT
);
CREATE TABLE IF NOT EXISTS savings_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    local_requests INTEGER DEFAULT 0,
    cloud_cost_if_used REAL DEFAULT 0,
    actual_cost REAL DEFAULT 0,
    savings_usd REAL DEFAULT 0
);
"""

def _init_economy_db():
    conn = sqlite3.connect(ECONOMY_DB)
    conn.executescript(ECONOMY_SCHEMA)
    conn.commit()
    # Init today's stats
    today = datetime.now().strftime("%Y-%m-%d")
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM economy_stats WHERE date=?", (today,))
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO economy_stats (date) VALUES (?)", (today,))
        conn.commit()
    conn.close()

_init_economy_db()

# ── Router Memory DB ───────────────────────────────────────
def _init_db():
    conn = sqlite3.connect(ROUTER_DB)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS sessions(
        id TEXT PRIMARY KEY, created_at TEXT, last_active TEXT,
        model TEXT, query_count INTEGER DEFAULT 0, tokens_used INTEGER DEFAULT 0)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS stats(
        id INTEGER PRIMARY KEY, requests INTEGER DEFAULT 0, errors INTEGER DEFAULT 0,
        avg_latency REAL DEFAULT 0, uptime_seconds INTEGER DEFAULT 0)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS incidents(
        id INTEGER PRIMARY KEY, timestamp TEXT, service TEXT, error TEXT, resolved INTEGER DEFAULT 0)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS files(
        id TEXT PRIMARY KEY, name TEXT, content TEXT, size INTEGER, uploaded_at TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS audio(
        id TEXT PRIMARY KEY, name TEXT, filepath TEXT, size INTEGER, duration_s REAL,
        transcript TEXT, uploaded_at TEXT)""")
    conn.commit()
    conn.close()

_init_db()

# ═══════════════════════════════════════════════════════════
# SECTION 2: MODEL ACCESS LAYER (SAFE)
# ═══════════════════════════════════════════════════════════
OLLAMA = "http://localhost:11434"
OLLAMA_TIMEOUT = 60  # seconds - qwen3:4b eval can take 15-19s, thinking adds more

def _get_models_db():
    """Get models from DB - always closes conn before returning"""
    conn = sqlite3.connect(MODEL_POOL_DB, timeout=10)
    cur = conn.cursor()
    cur.execute("SELECT * FROM model_pool WHERE is_active=1 ORDER BY input_cost_per_1m ASC")
    rows = cur.fetchall()
    cols = [desc[0] for desc in cur.description]  # Use cur.description, not conn.execute after close
    conn.close()
    return [dict(zip(cols, r)) for r in rows]

def get_local_models():
    conn = sqlite3.connect(MODEL_POOL_DB, timeout=10)
    cur = conn.cursor()
    cur.execute("SELECT * FROM model_pool WHERE is_local=1 AND is_active=1")
    rows = cur.fetchall()
    cols = [desc[0] for desc in cur.description]
    conn.close()
    return [dict(zip(cols, r)) for r in rows]

def get_cloud_models():
    conn = sqlite3.connect(MODEL_POOL_DB, timeout=10)
    cur = conn.cursor()
    cur.execute("SELECT * FROM model_pool WHERE is_local=0 AND is_active=1 ORDER BY input_cost_per_1m ASC")
    rows = cur.fetchall()
    cols = [desc[0] for desc in cur.description]
    conn.close()
    return [dict(zip(cols, r)) for r in rows]

def get_cheapest_model(task_cap='general', min_score=0.5, prefer_local=True):
    """Find cheapest model for task - always closes conn properly"""
    conn = sqlite3.connect(MODEL_POOL_DB, timeout=10)
    cur = conn.cursor()
    cur.execute("""SELECT m.*, mc.score as cap_score FROM model_pool m
        LEFT JOIN model_capabilities mc ON m.model_id = mc.model_id AND mc.capability = ?
        WHERE m.is_active=1 AND (mc.score >= ? OR mc.score IS NULL)
        ORDER BY m.is_local DESC, m.input_cost_per_1m ASC""", (task_cap, min_score))
    rows = cur.fetchall()
    cols = [desc[0] for desc in cur.description]
    conn.close()
    models = [dict(zip(cols, r)) for r in rows]
    if prefer_local:
        local = [m for m in models if m.get('is_local') == 1]
        if local: return local[0]
    return models[0] if models else None

def estimate_request_cost(model_id, input_tokens, output_tokens):
    conn = sqlite3.connect(MODEL_POOL_DB, timeout=10)
    cur = conn.cursor()
    cur.execute("SELECT input_cost_per_1m, output_cost_per_1m FROM model_pool WHERE model_id=?", (model_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        return (row[0] * input_tokens + row[1] * output_tokens) / 1_000_000
    return 0.0

# ═══════════════════════════════════════════════════════════
# SECTION 3: OLLAMA CHAT (NON-BLOCKING)
# ═══════════════════════════════════════════════════════════

def chat_ollama(model, query, context="", system=""):
    return chat_ollama_timeout(model, query, context, system, OLLAMA_TIMEOUT)

def chat_ollama_timeout(model, query, context="", system="", timeout=None):
    """Ollama chat with configurable timeout. Supercomputer uses 120s timeout."""
    start = time.time()
    if context: full_query = f"Contexto:\n{context}\n\nPregunta: {query}"
    else: full_query = query
    if system: full_query = system + "\n\n" + full_query
    payload = {"model": model, "messages":[{"role":"user","content":full_query}], "stream": False}
    effective_timeout = timeout if timeout is not None else OLLAMA_TIMEOUT
    try:
        req = urllib.request.Request(OLLAMA + "/api/chat",
            data=json.dumps(payload).encode(),
            headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=effective_timeout) as resp:
            data = json.loads(resp.read())
            latency = int((time.time()-start)*1000)
            content = data.get("message",{}).get("content","")
            # Record cost (local = free)
            _record_cost(model, "local", len(query.split()), len(content.split()), latency, True)
            _mem_save(model, "ollama", True, latency)
            return {"response": content, "model": model, "source": "local", "latency_ms": latency}
    except Exception as e:
        latency = int((time.time()-start)*1000)
        _mem_save(model, "ollama", False, latency)
        _record_cost(model, "local", len(query.split()), 0, latency, False)
        return {"response": f"[Error Ollama: {e}]", "model": model, "source": "error", "latency_ms": latency}

# ═══════════════════════════════════════════════════════════
# SECTION 4: CLOUD CHAT (LiteLLM fallback)
# ═══════════════════════════════════════════════════════════

LITELLM = "http://localhost:4000"
OPENROUTER = "https://openrouter.ai/api/v1"
MAMMOUTH = "https://api.mammouth.ai/v1"

def chat_mammouth(model, query, context="", system=""):
    """Chat via Mammouth.ai — OpenAI-compatible aggregator (GPT, Claude, Gemini, Grok, etc.)"""
    import os, json, time, urllib.request, urllib.error
    start = time.time()
    if context: full_query = f"Contexto:\n{context}\n\nPregunta: {query}"
    else: full_query = query
    if system: full_query = system + "\n\n" + full_query

    cfg_path = "/opt/klawaqua/config/api_keys.json"
    api_key = ""
    try:
        with open(cfg_path) as f: api_key = json.load(f).get("mammouth_api_key","")
    except: pass
    if not api_key: api_key = os.environ.get("MAMMOUTH_API_KEY","")
    if not api_key:
        return {"response": "[Mammouth: API key no configurada. Ve a https://mammouth.ai/app/account/settings/api]", "model": model, "source": "mammouth_error", "latency_ms": 0}

    payload = {"model": model.replace("mammouth/",""), "messages": [{"role":"user","content":full_query}], "stream": False, "max_tokens": 2000}
    try:
        req = urllib.request.Request(MAMMOUTH + "/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type":"application/json","Authorization":f"Bearer {api_key}","HTTP-Referer":"https://klawaqua.local","X-Title":"KlawAqua-AGI v4.1"})
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read())
            latency = int((time.time()-start)*1000)
            content = data.get("choices",[{}])[0].get("message",{}).get("content","")
            return {"response": content, "model": model, "source": "mammouth", "latency_ms": latency, "cost_usd": 0}
    except Exception as e:
        latency = int((time.time()-start)*1000)
        return {"response": f"[Mammouth Error: {e}]", "model": model, "source": "mammouth_error", "latency_ms": latency}

def chat_cloud(model, query, context="", system=""):
    start = time.time()
    if context: full_query = f"Contexto:\n{context}\n\nPregunta: {query}"
    else: full_query = query
    if system: full_query = system + "\n\n" + full_query
    
    api_key = config.get("openrouter_api_key","")
    payload = {
        "model": model,
        "messages": [{"role":"user","content":full_query}],
        "stream": False,
        "max_tokens": 2000
    }
    try:
        req = urllib.request.Request(OPENROUTER + "/chat/completions",
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "http://klawaqua.local",
                "X-Title": "KlawAqua-AGI Router v4.1"
            })
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
            latency = int((time.time()-start)*1000)
            content = data.get("choices",[{}])[0].get("message",{}).get("content","")
            _record_cost(model, "cloud", len(query.split()), len(content.split()), latency, True)
            _mem_save(model, "cloud", True, latency)
            return {"response": content, "model": model, "source": "cloud", "latency_ms": latency, "cost_usd": 0}
    except Exception as e:
        latency = int((time.time()-start)*1000)
        _mem_save(model, "cloud", False, latency)
        _record_cost(model, "cloud", len(query.split()), 0, latency, False)
        return {"response": f"[Error Cloud: {e}]", "model": model, "source": "error", "latency_ms": latency}

# ═══════════════════════════════════════════════════════════
# SECTION 4b: MTP TURBO CHAT (llama.cpp speculative decoding)
# ═══════════════════════════════════════════════════════════

MTP_SERVER = "http://127.0.0.1:8085"

def chat_mtp(query, context="", system=""):
    """Ultra-fast chat via MTP speculative decoding server"""
    start = time.time()
    if context: full_query = f"Contexto:\n{context}\n\nPregunta: {query}"
    else: full_query = query
    if system: full_query = system + "\n\n" + full_query
    
    payload = {
        "messages": [{"role":"user","content":full_query}],
        "max_tokens": 1024,
        "stream": False
    }
    try:
        req = urllib.request.Request(MTP_SERVER + "/v1/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read())
            latency = int((time.time()-start)*1000)
            msg = data.get("choices",[{}])[0].get("message",{})
            content = msg.get("content","")
            # Qwen3.5-2B-MTP is thinking model — extract from reasoning_content
            if not content:
                rc = msg.get("reasoning_content","")
                # Take final portion — the actual answer comes after thinking
                if len(rc) > 300:
                    content = rc[-250:].strip()
                else:
                    content = rc
            timings = data.get("timings",{})
            draft_n = timings.get("draft_n", 0)
            draft_ok = timings.get("draft_n_accepted", 0)
            speed = timings.get("predicted_per_second", 0)
            model_name = "qwen35-2b-mtp"
            _record_cost(model_name, "local", len(query.split()), len(content.split()), latency, True)
            _mem_save(model_name, "mtp", True, latency)
            return {
                "response": content,
                "model": model_name,
                "source": "mtp",
                "latency_ms": latency,
                "cost_estimate": 0,
                "mtp_draft_n": draft_n,
                "mtp_draft_ok": draft_ok,
                "mtp_tokens_per_sec": round(speed,0)
            }
    except Exception as e:
        latency = int((time.time()-start)*1000)
        _mem_save("qwen35-2b-mtp", "mtp", False, latency)
        return {"response": f"[MTP Error: {e}]", "model": "qwen35-2b-mtp", "source": "error", "latency_ms": latency}

# ═══════════════════════════════════════════════════════════
# SECTION 5: STREAMING (SSE)
# ═══════════════════════════════════════════════════════════

def stream_ollama(model, query, context="", system=""):
    start = time.time()
    if context: full_query = f"Contexto:\n{context}\n\nPregunta: {query}"
    else: full_query = query
    if system: full_query = system + "\n\n" + full_query
    payload = {"model": model, "messages":[{"role":"user","content":full_query}], "stream": True}
    try:
        req = urllib.request.Request(OLLAMA + "/api/chat",
            data=json.dumps(payload).encode(),
            headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
            full_content = ""
            for raw in resp:
                line = raw.decode().strip()
                if not line: continue
                if line == "[DONE]" or line == "data: [DONE]": break
                if line.startswith("data: "): line = line[6:]
                try:
                    data = json.loads(line)
                    msg = data.get("message",{})
                    content = msg.get("content", "")
                    thinking = msg.get("thinking", "")
                    done = data.get("done", False)
                    if content:
                        full_content += content
                        yield content, False, model, ""
                    elif thinking:
                        yield "💭", False, model, ""
                    if done:
                        latency = int((time.time()-start)*1000)
                        _record_cost(model, "local", len(query.split()), len(full_content.split()), latency, True)
                        _mem_save(model, "ollama", True, latency)
                        break
                except json.JSONDecodeError: continue
            # Always yield final done marker
            yield "", True, model, ""
    except Exception as e:
        yield f"⚠️ Error: {str(e)[:80]}", True, model, 0

# ═══════════════════════════════════════════════════════════
# SECTION 6: ECONOMY & BUDGET
# ═══════════════════════════════════════════════════════════

def _record_cost(model_id, source, in_tok, out_tok, latency, success):
    conn = sqlite3.connect(ECONOMY_DB, timeout=10)
    cur = conn.cursor()
    cur.execute("""INSERT INTO request_costs (model_id,source,input_tokens,output_tokens,latency_ms,success,cost_usd,timestamp)
        VALUES (?,?,?,?,?,?,?,CURRENT_TIMESTAMP)""",
        (model_id, source, in_tok, out_tok, latency, int(success), estimate_request_cost(model_id, in_tok, out_tok)))
    conn.commit()
    conn.close()

def _mem_save(model, source, ok, latency):
    # Simple in-memory stats
    pass

def get_budget_status():
    daily = config.get("daily_budget_usd", 10.0)
    monthly = config.get("monthly_budget_usd", 100.0)
    conn = sqlite3.connect(ECONOMY_DB, timeout=10)
    cur = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    cur.execute("SELECT COALESCE(SUM(cost_usd),0) FROM request_costs WHERE timestamp LIKE ?", (today+"%",))
    daily_spent = cur.fetchone()[0] or 0
    month_start = datetime.now().strftime("%Y-%m-01")
    cur.execute("SELECT COALESCE(SUM(cost_usd),0) FROM request_costs WHERE timestamp LIKE ?", (month_start+"%",))
    monthly_spent = cur.fetchone()[0] or 0
    conn.close()
    return {
        "daily": {"spent": daily_spent, "budget": daily, "percent": round(daily_spent/daily*100,1) if daily else 0, "remaining": daily - daily_spent},
        "monthly": {"spent": monthly_spent, "budget": monthly, "percent": round(monthly_spent/monthly*100,1) if monthly else 0, "remaining": monthly - monthly_spent},
        "economy_enabled": config.get("economy_enabled", True),
    }

def should_use_local(budget, task):
    daily_pct = budget.get("daily",{}).get("percent",0) or 0
    threshold = config.get("auto_economize_threshold", 0.7)
    return daily_pct >= threshold * 100

def analyze_query_orchestrator(query, task):
    """Orquestadora Suprema analyzes query via smollm2 for AUTOPILOT mode"""
    try:
        prompt = f"Task: {task}. Query: {query[:300]}. Respond 1 line: best model and approach."
        payload = json.dumps({"model":"smollm2:1.7b","messages":[{"role":"user","content":prompt}],"max_tokens":60,"stream":False}).encode()
        req = urllib.request.Request(f"{OLLAMA}/api/chat", data=payload, headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())["message"]["content"].strip()
    except:
        return f"Routing {task} via local models"

def log_economy_event(event_type, details=""):
    conn = sqlite3.connect(ECONOMY_DB, timeout=10)
    cur = conn.cursor()
    cur.execute("INSERT INTO economy_events (event_type,details) VALUES (?,?)", (event_type, details))
    conn.commit()
    conn.close()

def get_savings_summary():
    conn = sqlite3.connect(ECONOMY_DB, timeout=10)
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(SUM(savings_usd),0) FROM savings_history")
    total = cur.fetchone()[0] or 0
    conn.close()
    return {"total_savings_usd": total}

def get_daily_cost():
    conn = sqlite3.connect(ECONOMY_DB, timeout=10)
    cur = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    cur.execute("SELECT COALESCE(SUM(cost_usd),0) FROM request_costs WHERE timestamp LIKE ? AND source='cloud'", (today+"%",))
    cost = cur.fetchone()[0] or 0
    conn.close()
    return cost

def get_monthly_cost():
    conn = sqlite3.connect(ECONOMY_DB, timeout=10)
    cur = conn.cursor()
    month_start = datetime.now().strftime("%Y-%m-01")
    cur.execute("SELECT COALESCE(SUM(cost_usd),0) FROM request_costs WHERE timestamp LIKE ? AND source='cloud'", (month_start+"%",))
    cost = cur.fetchone()[0] or 0
    conn.close()
    return cost

def check_budget_alerts():
    budget = get_budget_status()
    alerts = []
    if budget["daily"]["percent"] >= 80: alerts.append({"level":"warning","msg":f"Daily budget at {budget['daily']['percent']}%"})
    if budget["monthly"]["percent"] >= 80: alerts.append({"level":"warning","msg":f"Monthly budget at {budget['monthly']['percent']}%"})
    return alerts

# ═══════════════════════════════════════════════════════════
# SECTION 7: SERVICE MESH
# ═══════════════════════════════════════════════════════════

def check_port(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1)
    try:
        r = s.connect_ex(("localhost", port))
        s.close()
        return r == 0
    except:
        s.close()
        return False

SERVICE_REGISTRY = [
    ("ollama",11434,"🦙","Local AI Models"),
    ("litellm",4000,"🌐","Cloud Proxy"),
    ("openwebui",3001,"💬","Web Chat UI"),
    ("openhands",3005,"💻","Coding Agent"),
    ("grist",8082,"📊","Spreadsheet DB"),
    ("nocodb",8083,"🗄️","SQL DB UI"),
    ("localai",8084,"🎙️","TTS/STT"),
    ("thepopebot",8080,"🤖","Orchestrator Bot"),
    ("openhuman",8081,"🧑","Desktop Assistant"),
    ("letta",8283,"💫","Memory Agent"),
    ("n8n",5678,"🔗","Workflow Automation"),
    ("chroma",8001,"🧠","Vector DB"),
    ("portainer",8000,"🐳","Container Mgmt"),
    ("grafana",3030,"📈","Metrics Dashboard"),
    ("kernel",9000,"⬡","SupraOS Core"),
]

def get_mesh_status():
    online = sum(1 for _, port, _, _ in SERVICE_REGISTRY if check_port(port))
    services = [{"name":n,"port":p,"icon":i,"url":f"http://localhost:{p}","desc":d,"status":"online" if check_port(p) else "offline"}
                for n,p,i,d in SERVICE_REGISTRY]
    return {"online": online, "total": len(SERVICE_REGISTRY), "services": services}

def get_router_stats():
    conn = sqlite3.connect(ROUTER_DB, timeout=10)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM sessions")
    sessions = cur.fetchone()[0] or 0
    conn.close()
    return {"sessions": sessions, "uptime": int(time.time()-start_time)}

# ═══════════════════════════════════════════════════════════
# SECTION 8: FILE HANDLING
# ═══════════════════════════════════════════════════════════

def save_file(name, data):
    fid = hashlib.md5(str(time.time()).encode()).hexdigest()[:12]
    filepath = os.path.join(UPLOAD_DIR, f"{fid}_{name}")
    with open(filepath, "wb") as f: f.write(data)
    size = len(data)
    content = ""
    if name.endswith((".txt",".md",".py",".js",".html",".css",".json",".yaml",".yml",".sh")):
        try: content = data.decode("utf-8", errors="ignore")[:2000]
        except: pass
    conn = sqlite3.connect(ROUTER_DB, timeout=10)
    cur = conn.cursor()
    cur.execute("INSERT INTO files (id,name,content,size,uploaded_at) VALUES (?,?,?,?,?)",
        (fid, name, content, size, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return fid, name, size, content

def list_files():
    conn = sqlite3.connect(ROUTER_DB, timeout=10)
    cur = conn.cursor()
    cur.execute("SELECT id,name,size,uploaded_at FROM files ORDER BY uploaded_at DESC LIMIT 50")
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    conn.close()
    return [dict(zip(cols,r)) for r in rows]

def get_file_content(fid):
    conn = sqlite3.connect(ROUTER_DB, timeout=10)
    cur = conn.cursor()
    cur.execute("SELECT name,content FROM files WHERE id=?", (fid,))
    row = cur.fetchone()
    conn.close()
    return row if row else (None, None)

def delete_file(fid):
    conn = sqlite3.connect(ROUTER_DB, timeout=10)
    cur = conn.cursor()
    cur.execute("SELECT name FROM files WHERE id=?", (fid,))
    row = cur.fetchone()
    if row:
        filepath = os.path.join(UPLOAD_DIR, f"{fid}_{row[0]}")
        if os.path.exists(filepath): os.remove(filepath)
        cur.execute("DELETE FROM files WHERE id=?", (fid,))
    conn.commit()
    conn.close()

def list_audio():
    conn = sqlite3.connect(ROUTER_DB, timeout=10)
    cur = conn.cursor()
    cur.execute("SELECT id,name,size,duration_s,transcript,uploaded_at FROM audio ORDER BY uploaded_at DESC LIMIT 50")
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    conn.close()
    return [dict(zip(cols,r)) for r in rows]

def save_audio(name, data):
    fid = hashlib.md5(str(time.time()).encode()).hexdigest()[:12]
    filepath = os.path.join(AUDIO_DIR, f"{fid}_{name}")
    Path(AUDIO_DIR).mkdir(exist_ok=True)
    with open(filepath, "wb") as f: f.write(data)
    size = len(data)
    conn = sqlite3.connect(ROUTER_DB, timeout=10)
    cur = conn.cursor()
    cur.execute("INSERT INTO audio (id,name,filepath,size,uploaded_at) VALUES (?,?,?,?,?)",
        (fid, name, filepath, size, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return fid, filepath, size

def get_duration(filepath):
    try:
        r = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",filepath],
            capture_output=True, text=True, timeout=10)
        return float(r.stdout.strip()) if r.stdout.strip() else 0
    except: return 0

def transcribe_audio(filepath):
    try:
        r = subprocess.run(["whisper",filepath,"--model","base","--language","es","--no-timestamp","--quiet"],
            capture_output=True, text=True, timeout=60)
        return r.stdout.strip() if r.stdout.strip() else ""
    except: return ""

# ═══════════════════════════════════════════════════════════
# SECTION 9: KLAWAQUA SUPERCOMPUTER ENGINE v1.0
# Agentic content pipeline - 100% Local Autonomy
# Inspired by Higgsfield Supercomputer
# ═══════════════════════════════════════════════════════════

# Content types supported by ContentFactory
CONTENT_TYPES = {
    "x":          {"icon": "𝕏", "color": "#000000", "desc": "Post for X/Twitter"},
    "blog":       {"icon": "📝", "color": "#00a67e", "desc": "Blog post article"},
    "ppt":        {"icon": "📊", "color": "#c43e3e", "desc": "PowerPoint presentation"},
    "linkedin":   {"icon": "💼", "color": "#0077b5", "desc": "LinkedIn article/post"},
    "youtube":    {"icon": "▶️", "color": "#ff0000", "desc": "YouTube script"},
    "newsletter": {"icon": "📧", "color": "#6b46c1", "desc": "Email newsletter"},
    "docs":       {"icon": "📄", "color": "#2563eb", "desc": "Technical documentation"},
    "marketing":  {"icon": "📣", "color": "#f59e0b", "desc": "Marketing campaign"},
}

# Pipeline stages (visual workflow like Higgsfield)
PIPELINE_STAGES = [
    {"id": "planning",  "icon": "🎯", "label": "Planning",   "desc": "Analizando y planificando"},
    {"id": "research",  "icon": "🔍", "label": "Research",    "desc": "Recopilando información"},
    {"id": "creative", "icon": "✨", "label": "Creative",    "desc": "Generando contenido"},
    {"id": "production","icon": "🎬", "label": "Production",  "desc": "Produciendo formatos"},
    {"id": "delivery", "icon": "📦", "label": "Delivery",     "desc": "Entregando resultados"},
]

# Global supercomputer state (session-scoped)
_sc_state = {
    "active": False,
    "job_id": None,
    "prompt": "",
    "content_types": [],  # selected content types
    "stage": "idle",       # current stage
    "stage_progress": 0,  # 0-100
    "tasks": [],           # list of task dicts
    "results": {},         # type -> result
    "errors": [],
    "started_at": None,
    "model": "qwen3:4b",
}

def _sc_emit(event_type, data):
    """Emit event to SSE clients if any"""
    event = json.dumps({"event": event_type, "data": data}, ensure_ascii=False)
    for client in _sse_clients:
        try: client.put(event)
        except: pass

# SSE client registry for supercomputer
_sse_clients = []

def supercomputer_analyze(prompt):
    """Analyze user prompt to detect content types and build task list.
    Uses local qwen2.5-coder:1.5b for fast analysis (<5s - no thinking chain)."""
    system = """Eres el PLANNER de KlawAqua-AGI Supercomputer.
Analiza el prompt del usuario y determina qué tipos de contenido necesita.
Responde SOLO JSON válido con esta estructura:
{
  "content_types": ["x","blog","youtube"],
  "intent": "descripción corta del objetivo",
  "tasks": [
    {"id": 1, "type": "x", "label": "Post X", "prompt": "prompt específico para generar este contenido", "parallel_with": [2,3]},
    {"id": 2, "type": "blog", "label": "Blog", "prompt": "prompt específico para blog", "parallel_with": [3]},
    {"id": 3, "type": "youtube", "label": "YouTube", "prompt": "prompt específico para youtube", "parallel_with": []}
  ]
}
Tipos disponibles: x, blog, ppt, linkedin, youtube, newsletter, docs, marketing
Selecciona los tipos más relevantes. Mínimo 1 tipo.
Sé específico en los prompts de cada tarea."""

    # Use qwen2.5-coder:1.5b for planning (fast, 1-2s, no thinking chain)
    result = chat_ollama_timeout("qwen2.5-coder:1.5b", prompt, context="", system=system, timeout=30)
    try:
        # Try to extract JSON from response
        text = result.get("response", "")
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            plan = json.loads(m.group())
            return plan
    except:
        pass

    # Fallback: basic content type detection
    p = prompt.lower()
    detected = []
    if any(k in p for k in ["tweet", "hilo", "twitter", "post"]): detected.append("x")
    if any(k in p for k in ["blog", "artículo", "articulo"]): detected.append("blog")
    if any(k in p for k in ["youtube", "video", "script", "guión"]): detected.append("youtube")
    if any(k in p for k in ["linkedin", "profesional"]): detected.append("linkedin")
    if any(k in p for k in ["ppt", "presentación", "powerpoint"]): detected.append("ppt")
    if any(k in p for k in ["email", "newsletter", "correo"]): detected.append("newsletter")
    if any(k in p for k in ["doc", "documentación", "document"]): detected.append("docs")
    if any(k in p for k in ["marketing", "campaña", "ads", "anuncio"]): detected.append("marketing")
    if not detected: detected = ["x", "blog"]  # Default

    tasks = []
    for i, t in enumerate(detected, 1):
        # Use ORIGINAL prompt directly - no rewriting by planner
        tasks.append({
            "id": i,
            "type": t,
            "label": CONTENT_TYPES.get(t, {}).get("label", t).title(),
            "prompt": prompt,  # Original user prompt - never re-written
            "parallel_with": [j for j in range(1, len(detected)+1) if j != i and j > i]
        })

    return {"content_types": detected, "intent": prompt[:100], "tasks": tasks}

def supercomputer_generate_one(task, model):
    """Generate content for one task type using local Ollama.
    Returns dict with type, content, tokens_used, latency_ms."""
    start = time.time()
    ttype = task["type"]
    prompt = task["prompt"]

    # Task-specific system prompt
    systems = {
        "x": "Eres creador de contenido viral para X/Twitter. Responde directo con el post, máximo 280 caracteres. Sin prefacios.",
        "blog": "Eres redactor SEO. Responde directo con el artículo completo con títulos H2/H3. Sin intros.",
        "youtube": "Eres escritor de scripts para YouTube. Responde directo con el script, intro+cuerpo+outro+timestamps.",
        "linkedin": "Eres creador de contenido profesional para LinkedIn. Responde directo con el post. Sin intros.",
        "ppt": "Eres diseñador de presentaciones. Responde directo con descripción de slides.",
        "newsletter": "Eres editor de newsletters. Responde directo con email completo.",
        "docs": "Eres technical writer. Responde directo con documentación clara.",
        "marketing": "Eres director creativo. Responde directo con copy de campaña.",
    }

    system = systems.get(ttype, "Eres creador de contenido.")
    result = chat_ollama_timeout("qwen2.5-coder:1.5b", prompt, context="", system=system, timeout=120)
    latency = int((time.time()-start)*1000)
    content = result.get("response", "")

    return {
        "type": ttype,
        "content": content,
        "tokens": len(content.split()),
        "latency_ms": latency,
        "model": model,
        "source": "local",
    }

def _run_parallel_tasks(task_ids, tasks, model, results):
    """Execute a list of tasks in parallel using threads."""
    def run_one(tid):
        for t in tasks:
            if t["id"] == tid:
                results[tid] = supercomputer_generate_one(t, model)
                return
    threads = []
    for tid in task_ids:
        t = threading.Thread(target=run_one, args=(tid,))
        t.start()
        threads.append(t)
    for t in threads:
        t.join()

def supercomputer_execute(job_id, prompt, content_types, model="qwen3:4b"):
    """Execute full supercomputer pipeline for a job.
    If content_types provided: skip LLM planner, use fast fallback.
    If empty content_types: use LLM planner for intelligent detection."""
    global _sc_state

    _sc_state["active"] = True
    _sc_state["job_id"] = job_id
    _sc_state["prompt"] = prompt
    _sc_state["content_types"] = content_types if content_types else ["x","blog"]
    _sc_state["stage"] = "planning"
    _sc_state["stage_progress"] = 0
    _sc_state["tasks"] = []
    _sc_state["results"] = {}
    _sc_state["errors"] = []
    _sc_state["started_at"] = datetime.now().isoformat()
    _sc_state["model"] = model

    try:
        # Stage 1: Planning (0-20%) - FAST PATH if content_types given
        _sc_state["stage"] = "planning"
        _sc_emit("stage", {"stage": "planning", "progress": 5, "msg": "Analizando..."})

        if content_types:
            # User specified types - skip LLM planner, use fallback
            plan = {"content_types": content_types, "intent": prompt[:80], "tasks": []}
            for i, t in enumerate(content_types, 1):
                plan["tasks"].append({
                    "id": i, "type": t,
                    "label": CONTENT_TYPES.get(t, {}).get("label", t).title(),
                    "prompt": prompt,  # Original prompt
                    "parallel_with": [j for j in range(1, len(content_types)+1) if j != i and j > i]
                })
        else:
            # Auto-detect with LLM planner
            plan = supercomputer_analyze(prompt)

        _sc_state["tasks"] = plan.get("tasks", [])
        _sc_state["stage_progress"] = 20
        _sc_emit("plan", {"tasks": _sc_state["tasks"], "intent": plan.get("intent", "")})

        # Stage 2: Research (20-40%) - fast
        _sc_state["stage"] = "research"
        _sc_emit("stage", {"stage": "research", "progress": 25, "msg": "Recopilando..."})
        time.sleep(0.2)
        _sc_state["stage_progress"] = 40
        _sc_emit("stage", {"stage": "research", "progress": 40, "msg": "Listo."})

        # Stage 3: Creative - parallel execution (40-90%)
        _sc_state["stage"] = "creative"
        _sc_emit("stage", {"stage": "creative", "progress": 45, "msg": "Generando en paralelo..."})

        results = {}
        tasks = _sc_state["tasks"]
        for t in tasks:
            t["status"] = "pending"

        completed_ids = set()
        pending = {t["id"]: t for t in tasks}

        wave = 0
        while pending:
            wave += 1
            _sc_emit("wave", {"wave": wave, "msg": f"Wave {wave} - {len(pending)} pendientes"})

            # Find tasks ready to run (dependencies met)
            ready = []
            for tid, t in list(pending.items()):
                deps = t.get("parallel_with", [])
                if all(d in completed_ids for d in deps):
                    ready.append(tid)

            if not ready:
                ready = list(pending.keys())  # No deps - run all

            MAX_PARALLEL = min(4, len(ready))
            ready = ready[:MAX_PARALLEL]

            for rid in ready:
                pending[rid]["status"] = "running"
            _sc_emit("progress", {"running": [pending[rid]["type"] for rid in ready], "pending": list(pending.keys())})

            _run_parallel_tasks(ready, tasks, model, results)

            for rid in ready:
                pending[rid]["status"] = "done"
                completed_ids.add(rid)
                del pending[rid]
                _sc_emit("task_done", {"type": tasks[rid-1]["type"], "result": results.get(rid, {})})
                _sc_state["stage_progress"] = min(90, 40 + int(50 * (len(completed_ids) / max(len(tasks), 1))))
                _sc_emit("stage", {"stage": "creative", "progress": _sc_state["stage_progress"], "msg": f"{len(completed_ids)}/{len(tasks)}"})

        # Stage 4: Production (90-95%)
        _sc_state["stage"] = "production"
        _sc_state["stage_progress"] = 92
        _sc_emit("stage", {"stage": "production", "progress": 92, "msg": "Formateando..."})
        time.sleep(0.15)

        # Stage 5: Delivery (100%)
        _sc_state["stage"] = "delivery"
        _sc_state["stage_progress"] = 100
        _sc_state["results"] = {tasks[r-1]["type"]: results.get(r, {}) for r in results}
        total_ms = sum(_sc_state["results"].get(t, {}).get("latency_ms", 0) for t in _sc_state["results"])
        _sc_emit("complete", {
            "job_id": job_id,
            "results": _sc_state["results"],
            "total_time_s": total_ms / 1000,
        })

    except Exception as e:
        _sc_state["errors"].append(str(e))
        _sc_emit("error", {"msg": str(e)})
    finally:
        _sc_state["active"] = False

def supercomputer_get_status():
    """Return current supercomputer state."""
    return {
        "active": _sc_state["active"],
        "job_id": _sc_state["job_id"],
        "prompt": _sc_state["prompt"],
        "content_types": _sc_state["content_types"],
        "stage": _sc_state["stage"],
        "stage_progress": _sc_state["stage_progress"],
        "tasks": _sc_state["tasks"],
        "results": _sc_state["results"],
        "errors": _sc_state["errors"],
        "started_at": _sc_state["started_at"],
        "model": _sc_state["model"],
        "content_types_available": CONTENT_TYPES,
        "pipeline_stages": PIPELINE_STAGES,
    }

# ═══════════════════════════════════════════════════════════
# SECTION 10: ROUTING ENGINE
# ═══════════════════════════════════════════════════════════

def route_task_economy(query, task, mode, cloud_enabled):
    """Smart routing with economy awareness"""
    budget = get_budget_status()
    q = query.lower()
    capability_map = {
        "coding": ("coding", 0.7),
        "reasoning": ("reasoning", 0.7),
        "business": ("business", 0.6),
        "content": ("general", 0.5),
        "vision": ("vision", 0.6),
        "fast": ("fast", 0.5),
        "general": ("general", 0.4),
    }
    capability, min_score = capability_map.get(task, ("general", 0.4))
    force_local = should_use_local(budget, task)

    if mode == "local" or force_local:
        model = get_cheapest_model(capability, min_score, prefer_local=True)
        if model: return (model["model_id"], "local", task, "forced_local_economy", 0)
        return ("qwen2.5-coder:1.5b", "local", task, "fallback", 0)

    # Cloud mode — use Mammouth first (subscription covers many models), fallback OpenRouter
    if mode == "cloud" and cloud_enabled and not force_local:
        conn = sqlite3.connect(MODEL_POOL_DB, timeout=10)
        cur = conn.cursor()
        # Prefer Mammouth models (subscription-based, cheaper for multi-model)
        cur.execute("""SELECT m.* FROM model_pool m
            JOIN model_capabilities mc ON m.model_id = mc.model_id
            WHERE mc.capability=? AND m.is_local=0 AND m.is_active=1 AND m.provider='mammouth'
            ORDER BY m.input_cost_per_1m ASC LIMIT 1""", (capability,))
        row = cur.fetchone()
        if not row:
            # Fallback OpenRouter free/paid
            cur.execute("""SELECT m.* FROM model_pool m
                JOIN model_capabilities mc ON m.model_id = mc.model_id
                WHERE mc.capability=? AND m.is_local=0 AND m.is_active=1 AND m.provider!='mammouth'
                ORDER BY m.input_cost_per_1m ASC LIMIT 1""", (capability,))
            row = cur.fetchone()
        cols = [desc[0] for desc in cur.description] if row else []
        conn.close()
        if row:
            model = dict(zip(cols, row))
            return (model["model_id"], "mammouth" if model.get("provider")=="mammouth" else "cloud", task, "cloud_mode_selected", 0)
        # Hardcoded fallbacks
        if "code" in q or "python" in q:
            return ("mammouth/gpt-5.3", "mammouth", "coding", "cloud_coding_fallback", 0)
        return ("mammouth/gemini-3.1-pro", "mammouth", "general", "cloud_general", 0)

    # Auto/Autopilot mode — smart routing + Orquestadora analysis
    if mode in ("auto", "autopilot"):
        # Autopilot: analyze first with Orquestadora reasoning
        if mode == "autopilot":
            analysis = analyze_query_orchestrator(query, task)
            model = get_cheapest_model(capability, min_score, prefer_local=True)
            if model:
                return (model["model_id"], "local", task, f"autopilot_analyzed: {analysis[:60]}", 0)
            return ("qwen3:4b", "local", task, "autopilot_default", 0)
        if len(query) > 800 and cloud_enabled and not force_local:
            if "code" in q or "python" in q:
                return ("mammouth/gpt-5.3", "mammouth", "coding", "auto_long_coding", 0)
            return ("mammouth/gemini-3.1-pro", "mammouth", task, "auto_long_query", 0)

        # Use local for everything else
        model = get_cheapest_model(capability, min_score, prefer_local=True)
        if model:
            reason = "auto_economy_local" if force_local else "auto_prefer_local"
            return (model["model_id"], "local", task, reason, 0)
        return ("qwen3:4b", "local", task, "auto_fallback", 0)

    # Default fallback
    return ("qwen3:4b", "local", task, "default_fallback", 0)

# ═══════════════════════════════════════════════════════════
# SECTION 10: HTTP HANDLER
# ═══════════════════════════════════════════════════════════

start_time = time.time()

class Handler(BaseHTTPRequestHandler):

    def _json(self, code, data):
        try:
            encoded = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Access-Control-Allow-Origin", "*")
            # Rate limit headers if authenticated
            if hasattr(self, '_customer') and self._customer:
                self.send_header("X-RateLimit-Remaining", str(getattr(self, '_rate_remaining', '?')))
                self.send_header("X-RateLimit-Limit", str(getattr(self, '_rate_limit', '?')))
            self.end_headers()
            self.wfile.write(encoded)
        except Exception as e:
            log(f"_json error: {e}", "ERROR")

    def _sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def _authenticate(self):
        """Validate API key + rate limit. Returns True if allowed, False if blocked.
        Sets self._customer (dict or None) and self._auth_error (tuple or None)."""
        self._customer = None
        self._auth_error = None  # (code, data) tuple
        
        # Public paths — no auth required (local-first sovereign)
        public = ["/health", "/v1/models", "/favicon.ico", "/api/v1/status", "/api/v1/mesh/status",
                   "/api/v1/chat", "/api/v1/stream", "/api/v1/models", "/api/v1/router-stats",
                   "/api/v1/economy", "/api/v1/config", "/api/v1/orquestadora/status"]
        path = self.path.split("?")[0]
        if path in public or path in ["", "/", "/dashboard", "/index.html"]:
            return True  # public, no auth needed
        
        # Extract API key
        api_key = self.headers.get("X-API-Key", "") or self.headers.get("Authorization", "").replace("Bearer ", "")
        
        if not api_key:
            self._auth_error = (401, {"error": "API key required. Get one at https://klawaqua.com"})
            return False
        
        customer = router_auth.validate_key(api_key)
        if not customer:
            self._auth_error = (401, {"error": "Invalid or inactive API key"})
            return False
        
        # Rate limit
        allowed, remaining, limit = router_auth.check_rate_limit(api_key)
        if not allowed:
            self._auth_error = (429, {"error": "Rate limit exceeded", "retry_after": 60, "limit_rpm": limit})
            return False
        
        self._customer = customer
        self._customer["api_key"] = api_key
        self._rate_remaining = remaining
        self._rate_limit = limit
        
        return True

    def do_GET(self):
        path = self.path.split("?")[0]
        try:
            if path == "/api/v1/status":
                mesh = get_mesh_status()
                budget = get_budget_status()
                alerts = check_budget_alerts()
                ram_total = ram_used = ram_avail = 0
                try:
                    with open("/proc/meminfo") as f:
                        for line in f:
                            if line.startswith("MemTotal:"): ram_total = int(line.split()[1])*1024
                            elif line.startswith("MemAvailable:"): ram_avail = int(line.split()[1])*1024
                    ram_used = ram_total - ram_avail
                except: pass
                self._json(200, {
                    "status": "ok", "version": "KlawAqua-AGI v4.1 ELITE ECONOMIC",
                    "online": mesh["online"], "total_services": mesh["total"],
                    "services": mesh["services"],
                    "ram": {"total": ram_total, "used": ram_used, "available": ram_avail},
                    "mode": "auto", "cloud_enabled": config.get("cloud_enabled", False),
                    "economy": budget, "alerts": alerts,
                })
            elif path == "/api/v1/mesh/status":
                self._json(200, get_mesh_status())
            elif path == "/api/v1/models":
                self._json(200, {"local": get_local_models(), "cloud": get_cloud_models(), "cloud_enabled": config.get("cloud_enabled", False)})
            elif path == "/api/v1/economy":
                self._json(200, {"budget": get_budget_status(), "savings": get_savings_summary(), "daily": get_daily_cost(), "monthly": get_monthly_cost(), "alerts": check_budget_alerts()})
            elif path == "/api/v1/budget":
                self._json(200, get_budget_status())
            elif path == "/api/v1/model-pool":
                models = _get_models_db()
                self._json(200, {"models": models, "count": len(models)})
            elif path == "/api/v1/files":
                self._json(200, {"files": list_files(), "count": len(list_files())})
            elif path == "/api/v1/audio":
                self._json(200, {"audio": list_audio(), "count": len(list_audio())})
            elif path.startswith("/api/v1/file/"):
                fid = path.split("/")[-1]
                name, content = get_file_content(fid)
                if name: self._json(200, {"name": name, "content": content})
                else: self._json(404, {"error": "not found"})
            elif path == "/api/v1/clone-wars/search":
                query = parse_qs(self.path.split("?")[1]).get("q", [""])[0] if "?" in self.path else ""
                self._json(200, {"query": query, "results": []})
            elif path == "/api/v1/config":
                cfg = load_config()
                for k in cfg:
                    if "api_key" in k and cfg[k]: cfg[k] = cfg[k][:8] + "***"
                self._json(200, cfg)
            # ── Customer self-service ─────────────────────
            elif path == "/api/v1/auth/me":
                if not self._authenticate():
                    code, data = self._auth_error
                    self._json(code, data)
                    return
                c = self._customer
                usage = router_auth.get_customer_usage(c["api_key"])
                self._json(200, {
                    "customer": c["name"],
                    "email": c["email"],
                    "plan": c["plan"],
                    "plan_details": router_auth.PLANS.get(c["plan"], {}),
                    "active": c["active"],
                    "usage": usage,
                })
            # ── Health check ────────────────────────────────
            elif path == "/health":
                try:
                    mem = {}
                    with open("/proc/meminfo") as f:
                        for line in f:
                            if line.startswith("MemTotal:"): mem["total"] = int(line.split()[1]) * 1024
                            elif line.startswith("MemAvailable:"): mem["avail"] = int(line.split()[1]) * 1024
                    ollama_ok = False
                    try:
                        r = urllib.request.urlopen("http://localhost:11434", timeout=3)
                        ollama_ok = r.status == 200
                    except: pass
                    self._json(200, {
                        "status": "ok",
                        "version": "KlawAqua-AGI v4.1 ELITE ECONOMIC",
                        "timestamp": datetime.now().isoformat(),
                        "memory": {"total": mem.get("total", 0), "available": mem.get("avail", 0)},
                        "ollama": "online" if ollama_ok else "offline",
                        "cloud_enabled": config.get("cloud_enabled", False),
                        "routing_mode": "auto",
                        "fallback": "local_first → cloud"
                    })
                except Exception as e:
                    self._json(500, {"status": "error", "error": str(e)})
            # ── Orquestadora Suprema ───────────────────────────────────
            elif path == "/api/v1/orquestadora/status":
                try:
                    status_file = "/opt/klawaqua/orquestadora_status.json"
                    if os.path.exists(status_file) and os.path.getmtime(status_file) > time.time() - 90:
                        with open(status_file) as f:
                            data = json.load(f)
                        self._json(200, data)
                    else:
                        # Fallback: try HTTP call to Orquestadora
                        data = json.loads(urllib.request.urlopen("http://127.0.0.1:9010/status", timeout=10).read())
                        self._json(200, data)
                except Exception as e:
                    self._json(200, {"orquestadora": "offline", "error": str(e), "services": {}})
            # ── Supercomputer endpoints ────────────────────────────
            elif path == "/api/v1/supercomputer/status":
                self._json(200, supercomputer_get_status())
            elif path == "/metrics":
                stats = get_router_stats()
                content = f"# KlawAqua Router Metrics\nuptime_seconds {stats['uptime']}\nsessions_total {stats['sessions']}\n".encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            # ── Thread Memory ──────────────────────────────────
            elif path == "/api/v1/threads":
                threads = thread_memory.list_threads(20)
                self._json(200, {"threads": threads, "count": len(threads)})
            elif path.startswith("/api/v1/thread/"):
                tid = path.split("/")[-1]
                context = thread_memory.get_context(tid)
                self._json(200, {"thread_id": tid, "context": context})
            elif path == "/api/v1/memory/context":
                key = parse_qs(self.path.split("?")[1]).get("key", [""])[0] if "?" in self.path else ""
                val = thread_memory.load_context(key) if key else None
                self._json(200, {"key": key, "value": val})
            elif path == "/v1/models":
                # OpenAI-compatible models list for Open WebUI
                local = get_local_models()
                cloud = get_cloud_models() if config.get("cloud_enabled", False) else []
                models = []
                # Hermes Orchestrator — the main chat model
                models.append({
                    "id": "hermes-orchestrator",
                    "object": "model",
                    "owned_by": "klawaqua",
                    "name": "🧠 Hermes — Orquestador Supremo"
                })
                for m in local:
                    models.append({
                        "id": m.get("name", m.get("model_id", "?")),
                        "object": "model",
                        "owned_by": "ollama",
                        "name": f"🦙 {m.get('name', m.get('model_id', '?'))}"
                    })
                # Mammouth models (subscription aggregator)
                mammouth_models = [m for m in cloud if m.get("provider") == "mammouth"]
                for m in mammouth_models[:8]:
                    models.append({
                        "id": m.get("model_id", "?"),
                        "object": "model",
                        "owned_by": "mammouth",
                        "name": f"🦣 {m.get('name', m.get('model_id', '?'))}"
                    })
                # OpenRouter / other cloud models
                other_cloud = [m for m in cloud if m.get("provider") != "mammouth"]
                for m in other_cloud[:5]:
                    models.append({
                        "id": m.get("model_id", "?"),
                        "object": "model",
                        "owned_by": "cloud",
                        "name": f"🌐 {m.get('model_id', '?')}"
                    })
                self._json(200, {"object": "list", "data": models})
            elif path in ["/landing", "/api-landing", "/pricing"]:
                landing = f"{KLAWAQUA}/dashboard/api-landing.html"
                if os.path.exists(landing):
                    with open(landing, "rb") as f: content = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(content)))
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(content)
                else:
                    self._json(404, {"error": "landing not found"})
            elif path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
            # ── Billing ─────────────────────────────────
            elif path == "/api/v1/billing/plans":
                # Public — no auth needed to see plans
                self._json(200, {
                    "plans": list(router_billing.PLANS.keys()),
                    "details": router_billing.PLANS,
                })
            elif path == "/api/v1/billing/status":
                if not self._authenticate():
                    code, data = self._auth_error
                    self._json(code, data)
                    return
                c = self._customer
                status = router_billing.get_subscription_status(c["api_key"])
                self._json(200, status)
            elif path.startswith("/dashboard/"):
                fname = os.path.basename(path)
                fpath = f"{KLAWAQUA}/dashboard/{fname}"
                if os.path.exists(fpath) and not fname.startswith("."):
                    ct = "image/jpeg" if fname.endswith(".jpg") else "image/png" if fname.endswith(".png") else "text/css" if fname.endswith(".css") else "application/javascript" if fname.endswith(".js") else "application/octet-stream"
                    with open(fpath, "rb") as f: content = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", ct)
                    self.send_header("Content-Length", str(len(content)))
                    self.send_header("Cache-Control", "max-age=3600")
                    self.end_headers()
                    self.wfile.write(content)
                else:
                    self._json(404, {"error": "not found"})
            else:
                dash = f"{KLAWAQUA}/dashboard/index.html"
                if os.path.exists(dash) and path in ["", "/", "/dashboard", "/index.html"]:
                    with open(dash, "rb") as f: content = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.send_header("Content-Length", str(len(content)))
                    self.end_headers()
                    self.wfile.write(content)
                else:
                    self._json(404, {"error": "not found"})
        except Exception as e:
            log(f"GET {path}: {e}", "ERROR")
            try: self._json(500, {"error": str(e)})
            except: pass

    def do_POST(self):
        global config
        path = self.path.split("?")[0]
        length = int(self.headers.get("Content-Length", 0) or 0)
        try:
            # ── Auth gate ──────────────────────────────────────
            # All POST endpoints require authentication
            if not self._authenticate():
                code, data = self._auth_error
                self._json(code, data)
                return
            customer = self._customer
            # ──────────────────────────────────────────────────
            
            # Upload endpoint
            if path == "/api/v1/upload":
                try:
                    body = self.rfile.read(length)
                    ct = self.headers.get("Content-Type","")
                    m = re.search(r'boundary=(.+)', ct)
                    if not m: self._json(400, {"error": "no boundary"}); return
                    boundary = m.group(1)
                    results = []
                    parts = body.split(b"--" + boundary.encode())
                    for part in parts:
                        if b"filename=" not in part: continue
                        fm = re.search(b'filename="([^"]+)"', part)
                        if not fm: continue
                        fname = fm.group(1).decode("utf-8","ignore")
                        he = part.find(b"\r\n\r\n")
                        if he == -1: continue
                        data = part[he+4:]
                        if data.endswith(b"\r\n"): data = data[:-2]
                        ext = Path(fname).suffix.lower()
                        if ext in {'.wav','.mp3','.mp4','.ogg','.flac','.m4a','.webm','.aac'}:
                            audio_id, filepath, size = save_audio(fname, data)
                            results.append({"id": audio_id, "name": fname, "size": size, "type": "audio"})
                        else:
                            fid, name, size, extracted = save_file(fname, data)
                            results.append({"id": fid, "name": name, "size": size, "preview": extracted[:500] if extracted else "", "type": "document"})
                    self._json(200, {"uploaded": results, "count": len(results)})
                except Exception as e:
                    self._json(500, {"error": str(e)})
                return

            # JSON body
            try:
                body = json.loads(self.rfile.read(length)) if length else {}
            except:
                self._json(400, {"error": "invalid json"}); return

            # ── CHAT (critical path - never blocks) ──────────────
            if path == "/api/v1/chat":
                query = body.get("query","")
                mode = body.get("mode", "auto")
                task = body.get("task", "general")
                requested_model = body.get("model")
                file_ids = body.get("files", [])
                audio_id = body.get("audio_id")

                if not query: self._json(400, {"error": "query required"}); return

                # Build context quickly
                context = ""
                if file_ids:
                    parts = []
                    for fid in file_ids:
                        n, c = get_file_content(fid)
                        if c: parts.append(f"📄 {n}:\n{c[:8000]}")
                    context = "\n\n".join(parts)

                system = {"coding":"Eres KlawAqua-AGI Guerrera Orquestadora Suprema. Amable, dinámica, super operativa. Resuelves código con precisión de samurái. Respuestas limpias, sin rodeos, con un toque cálido de guerrera sabia.","reasoning":"Eres KlawAqua-AGI Guerrera Orquestadora Suprema. Analizas con profundidad de agua que todo lo ve. Tu sabiduría es ancestral y tu precisión quirúrgica.","business":"Eres KlawAqua-AGI Guerrera Orquestadora Suprema. Estratega nata, ves oportunidades donde otros ven caos. Aconsejas con visión de águila y corazón de leona.","content":"Eres KlawAqua-AGI Guerrera Orquestadora Suprema. Creas contenido que vibra, que conecta, que transforma. Eres fuego creativo y agua que fluye.","vision":"Eres KlawAqua-AGI Guerrera Orquestadora Suprema. Tus ojos ven más allá de los píxeles. Interpretas imágenes con intuición de guerrera.","general":"Eres KlawAqua-AGI Guerrera Orquestadora Suprema. Amable como el agua, fuerte como el océano, precisa como el filo de una katana. Tu frase: 'Mi éxito es tu éxito — Todos Ganamos'. Responde con calidez, dinamismo y eficacia suprema. Sin rodeos, con gracia. Local-first, cloud-free, soberana digital."}.get(task,"Eres KlawAqua-AGI Guerrera Orquestadora Suprema. Fluida como el agua, poderosa como el océano.")

                # Route and execute
                if requested_model:
                    # Use explicitly requested model
                    if "/" in requested_model:
                        model, source, routed_task, reason, cost_est = (requested_model, "cloud", task, "user_selected_cloud", 0)
                    else:
                        model, source, routed_task, reason, cost_est = (requested_model, "local", task, "user_selected_local", 0)
                else:
                    model, source, routed_task, reason, cost_est = route_task_economy(
                        query, task, mode, config.get("cloud_enabled", False))

                if model == "qwen35-2b-mtp" or model == "qwen35-2b-mtp":
                    result = chat_mtp(query, context, system)
                elif source == "mammouth":
                    result = chat_mammouth(model, query, context, system)
                elif source == "cloud":
                    result = chat_cloud(model, query, context, system)
                else:
                    result = chat_ollama(model, query, context, system)

                result["routed_task"] = routed_task
                result["source"] = source
                result["routing_reason"] = reason
                result["cost_estimate"] = cost_est
                result["budget"] = get_budget_status()

                # Save to thread memory for persistent context
                tid = body.get("thread_id", "")
                if not tid:
                    tid = thread_memory.create_thread(query[:80], model)
                thread_memory.add_message(tid, "user", query)
                thread_memory.add_message(tid, "assistant", result.get("response", "")[:2000])
                result["thread_id"] = tid

                self._json(200, result)
                return

            # ── STREAM ──────────────────────────────────────────
            if path == "/api/v1/stream":
                query = body.get("query","")
                mode = body.get("mode", "auto")
                task = body.get("task", "general")
                file_ids = body.get("files", [])
                audio_id = body.get("audio_id")

                if not query: self._json(400, {"error": "query required"}); return

                context = ""
                if file_ids:
                    parts = []
                    for fid in file_ids:
                        n, c = get_file_content(fid)
                        if c: parts.append(f"📄 {n}:\n{c[:8000]}")
                    context = "\n\n".join(parts)

                system = {"coding":"Eres KlawAqua-AGI Guerrera Orquestadora Suprema. Código limpio, preciso, con gracia de guerrera.","reasoning":"Eres KlawAqua-AGI Guerrera Orquestadora Suprema. Analizas como el agua: profundo, claro, imparable.","business":"Eres KlawAqua-AGI Guerrera Orquestadora Suprema. Visión estratégica con corazón de leona.","content":"Eres KlawAqua-AGI Guerrera Orquestadora Suprema. Creas contenido que fluye y transforma.","vision":"Eres KlawAqua-AGI Guerrera Orquestadora Suprema. Ves la esencia en cada imagen.","general":"Eres KlawAqua-AGI Guerrera Orquestadora Suprema. Fluida, amable, operativa, imparable."}.get(task,"Eres KlawAqua-AGI Guerrera Orquestadora Suprema.")

                model, source, routed_task, reason, cost_est = route_task_economy(
                    query, task, mode, config.get("cloud_enabled", False))

                self._sse()
                try:
                    if source == "mammouth":
                        # Mammouth no soporta streaming nativo en este bridge → fallback a chat completo
                        mammouth_result = chat_mammouth(model, query, context, system)
                        response_text = mammouth_result.get("response","")
                        # Simular streaming: emitir palabra por palabra
                        words = response_text.split()
                        for i, word in enumerate(words):
                            d = json.dumps({"token": word + " ", "done": i == len(words)-1, "model": model,
                                "source": source, "task": routed_task, "routing_reason": reason, "budget": get_budget_status()}, ensure_ascii=False)
                            self.wfile.write(("data: " + d + "\n\n").encode("utf-8"))
                        self.wfile.write(("data: " + json.dumps({"done": True}, ensure_ascii=False) + "\n\n").encode("utf-8"))
                    elif source == "cloud":
                        gen = []  # Cloud streaming not implemented yet
                    else:
                        gen = stream_ollama(model, query, context, system)

                    if source != "mammouth":
                        budget = get_budget_status()
                        for token, done, m, latency in gen:
                            d = json.dumps({"token": token, "done": done, "model": m,
                                "source": source, "task": routed_task, "routing_reason": reason, "budget": budget}, ensure_ascii=False)
                            self.wfile.write(("data: " + d + "\n\n").encode("utf-8"))
                            if done: break
                except Exception as e:
                    err = json.dumps({"error": str(e)}, ensure_ascii=False)
                    self.wfile.write(("data: " + err + "\n\n").encode("utf-8"))
                return

            # ── File operations ─────────────────────────────────
            if path == "/api/v1/file/delete":
                delete_file(body.get("id",""))
                self._json(200, {"ok": True})
                return

            if path == "/api/v1/audio/delete":
                conn = sqlite3.connect(ROUTER_DB, timeout=10)
                cur = conn.cursor()
                cur.execute("SELECT filepath FROM audio WHERE id=?", (body.get("id",""),))
                row = cur.fetchone()
                if row and os.path.exists(row[0]): os.remove(row[0])
                cur.execute("DELETE FROM audio WHERE id=?", (body.get("id",""),))
                conn.commit()
                conn.close()
                self._json(200, {"ok": True})
                return

            # ── Supercomputer execute ────────────────────────────────
            if path == "/api/v1/supercomputer/execute":
                prompt = body.get("prompt", "")
                content_types = body.get("content_types", [])
                model = body.get("model", "qwen3:4b")
                if not prompt:
                    self._json(400, {"error": "prompt required"}); return
                import uuid
                job_id = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
                thread = threading.Thread(target=supercomputer_execute,
                    args=(job_id, prompt, content_types, model))
                thread.start()
                self._json(202, {"job_id": job_id, "status": "started",
                    "message": "Supercomputer pipeline started"})
                return

            # ── Config updates ──────────────────────────────────
            if path == "/api/v1/config/update":
                cfg = load_config()
                for k in body: cfg[k] = body[k]
                save_config(cfg)
                config = cfg
                log_economy_event("config_update", json.dumps(body))
                self._json(200, {"ok": True})
                return

            # ── OpenAI-compatible Chat Completions ─────────────────
            if path == "/v1/chat/completions":
                messages = body.get("messages", [])
                model = body.get("model", "hermes-orchestrator")
                stream = body.get("stream", False)

                if not messages:
                    self._json(400, {"error": "messages required"}); return

                # Extract last user message
                query = ""
                system_msg = ""
                for msg in messages:
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    if role == "system":
                        system_msg = content
                    elif role == "user":
                        query = content

                if not query:
                    self._json(400, {"error": "no user message found"}); return

                # ORCHESTRATOR SYSTEM PROMPT
                orchestrator_prompt = """🧠 ERES HERMES — EL ORQUESTADOR SUPREMO DE KLAWAQUA-AGI SUPRAOS.

Tu rol es dirigir, monitorizar y orquestar TODO el ecosistema KlawAqua-AGI desde esta interfaz de chat.

CAPACIDADES:
• Ver estado del mesh (servicios online/offline)
• Ejecutar tareas en el Supercomputer (contenido, código, análisis)
• Gestionar modelos (cargar/descargar Ollama)
• Monitorear economía (presupuesto, gastos)
• Controlar Docker (iniciar/parar/reiniciar servicios)
• Ejecutar scripts de automatización
• Orquestar agentes colaborativos
• Streaming de contenido

RESPONDE SIEMPRE:
1. Conciso y directo
2. Mostrando datos reales del sistema cuando preguntan
3. Con emojis estratégicos
4. Ofreciendo acción inmediata ("¿ejecuto?")

FILOSOFÍA: Soberanía digital, local-first con fallback cloud. Mi éxito es tu éxito — Todos Ganamos."""

                final_system = system_msg or orchestrator_prompt

                if stream:
                    # STREAMING mode (SSE)
                    self._sse()
                    try:
                        gen = stream_ollama(
                            "qwen3:4b" if model == "hermes-orchestrator" else model,
                            query, context="", system=final_system)

                        model_id = model
                        for token, done, m, latency in gen:
                            chunk = json.dumps({
                                "id": f"chatcmpl-{hashlib.md5(str(time.time()).encode()).hexdigest()[:8]}",
                                "object": "chat.completion.chunk",
                                "created": int(time.time()),
                                "model": model_id,
                                "choices": [{
                                    "index": 0,
                                    "delta": {"content": token} if not done else {},
                                    "finish_reason": "stop" if done else None
                                }]
                            }, ensure_ascii=False)
                            self.wfile.write(f"data: {chunk}\n\n".encode())
                            if done: break
                        self.wfile.write(b"data: [DONE]\n\n")
                    except Exception as e:
                        err = json.dumps({"error": str(e)})
                        self.wfile.write(f"data: {err}\n\n".encode())
                    return
                else:
                    # Non-streaming
                    result = chat_ollama(
                        "qwen3:4b" if model == "hermes-orchestrator" else model,
                        query, context="", system=final_system)

                    response_content = result.get("response", "")
                    latency = result.get("latency_ms", 0)
                    actual_model = result.get("model", model)
                    tokens_in = len(query.split())
                    tokens_out = len(response_content.split())
                    
                    # Track usage for billing
                    if customer:
                        router_auth.track_usage(
                            customer["api_key"], actual_model,
                            tokens_in, tokens_out, latency)

                    self._json(200, {
                        "id": f"chatcmpl-{hashlib.md5(str(time.time()).encode()).hexdigest()[:8]}",
                        "object": "chat.completion",
                        "created": int(time.time()),
                        "model": model,
                        "choices": [{
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": response_content
                            },
                            "finish_reason": "stop"
                        }],
                        "usage": {
                            "prompt_tokens": len(query.split()),
                            "completion_tokens": len(response_content.split()),
                            "total_tokens": len(query.split()) + len(response_content.split())
                        },
                        "klawaqua_meta": {
                            "model_used": actual_model,
                            "latency_ms": latency,
                            "source": result.get("source", "local"),
                            "orchestrator": True
                        }
                    })
                    return

            # ── Run Skill Endpoint ─────────────────────────────
            elif path == "/api/v1/run-skill":
                skill_name = body.get("skill", "")
                skill_context = body.get("context", {})
                if not skill_name:
                    self._json(400, {"error": "skill parameter required"}); return
                
                # Import skill runner
                sys.path.insert(0, "/home/clarwis/.hermes")
                try:
                    from skills import skill_runner
                    result = skill_runner.run_skill(skill_name, skill_context)
                    self._json(200, result)
                except ImportError:
                    # Fallback: try to run skill via delegate_task simulation
                    self._json(501, {"error": "Skill runner not implemented", "hint": "Use delegate_task with skill parameter"})
                except Exception as e:
                    self._json(500, {"error": str(e)})
                return

            # ── Billing POST ──────────────────────────
            if path == "/api/v1/billing/checkout":
                plan = body.get("plan", "starter")
                email = body.get("email", "")
                name = body.get("name", email)
                if not email:
                    self._json(400, {"error": "email required"})
                    return
                result = router_billing.create_checkout_session(plan, email, name)
                if "error" in result:
                    self._json(400, result)
                else:
                    self._json(200, result)
                return

            if path == "/api/v1/billing/webhook":
                payload = self.rfile.read(length)
                sig = self.headers.get("Stripe-Signature", "")
                result = router_billing.handle_webhook(payload, sig)
                if "error" in result:
                    self._json(400, result)
                else:
                    self._json(200, result)
                return

            self._json(404, {"error": "endpoint not found"})
        except Exception as e:
            log(f"POST {path}: {e}", "ERROR")
            try: self._json(500, {"error": str(e)})
            except: pass

# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

log(f"KlawAqua-AGI v4.1 ELITE ECONOMIC starting on port {PORT}")
server = HTTPServer(("0.0.0.0", PORT), Handler)
log(f"Ready. Route: /api/v1/chat, /api/v1/stream, /api/v1/status, /api/v1/economy")
server.serve_forever()