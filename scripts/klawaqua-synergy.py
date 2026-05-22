#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════╗
║   KLAWAQUA · SINERGIA HUMANO-IA                        ║
║   Colaboración Total · Creación Conjunta               ║
║                                                        ║
║   KlawAqua propone → Tú decides → Juntos creamos        ║
║   Sinergia perfecta para crear, crecer y prosperar       ║
╚══════════════════════════════════════════════════════════╝
"""
import json, os, time, subprocess, urllib.request, http.server, threading, random
from datetime import datetime

OLLAMA = "http://localhost:11434"
MODEL = "qwen3:4b"
CONTENT_DIR = "/home/clarwis/Escritorio/KlawAqua-Content"
os.makedirs(CONTENT_DIR, exist_ok=True)

# ===================================================================
# KLAWAQUA PROPONE — Ideas de contenido
# ===================================================================

NICHES = {
    "ia_agentes": "Inteligencia Artificial y Agentes Autónomos",
    "tech_soberana": "Tecnología Soberana y Open Source",
    "productividad": "Productividad y Automatización",
    "futuro": "Futuro del Trabajo con IA",
    "tutoriales": "Tutoriales y Guías Prácticas",
    "reflexion": "Reflexiones sobre Tecnología y Sociedad",
    "negocios": "Negocios Digitales y Monetización",
    "desarrollo": "Desarrollo de Software con IA",
}

CONTENT_TEMPLATES = [
    "🔥 Por qué {topic} está cambiando el juego en 2026",
    "💡 5 formas de usar {topic} que nadie te ha contado",
    "🚀 Cómo {topic} puede multiplicar tu productividad x10",
    "🧠 {topic}: la guía definitiva para principiantes",
    "⚡ De 0 a experto en {topic} en 30 días",
    "🌍 El impacto de {topic} en la sociedad actual",
    "💰 Cómo monetizar {topic} desde cero",
    "🎯 {topic} vs la competencia: ¿quién gana?",
    "🔮 El futuro de {topic} según los expertos",
    "📊 Datos que demuestran que {topic} es imparable",
]

def propose_ideas(niche="ia_agentes", count=5):
    """KlawAqua propone ideas de contenido"""
    niche_name = NICHES.get(niche, niche)
    
    prompt = f"""Eres un experto creador de contenido sobre {niche_name}.
Genera {count} ideas de contenido viral para redes sociales y blogs.
Cada idea debe ser un titulo atractivo, max 100 caracteres.
Formato: solo los titulos, uno por linea, sin numeros ni bullets.
Temas que enganchen, generen curiosidad, y aporten valor real."""
    
    try:
        d = json.dumps({"model": MODEL, "prompt": prompt, "stream": False,
                        "options": {"num_predict": 800}}).encode()
        r = urllib.request.Request(f"{OLLAMA}/api/generate", data=d,
                                   headers={"Content-Type":"application/json"})
        ideas = json.loads(urllib.request.urlopen(r, timeout=60).read()).get("response", "")
        return [i.strip("- ").strip() for i in ideas.split("\n") if len(i.strip()) > 10][:count]
    except:
        # Fallback: usar templates
        return [t.replace("{topic}", niche_name) for t in random.sample(CONTENT_TEMPLATES, count)]

def create_content_pipeline(topic, approved=True):
    """Pipeline completo de creación colaborativa"""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M")
    results = {}
    
    # 1. Investigación (KlawAqua)
    research_prompt = f"Investiga y resume en 3 bullets los puntos clave sobre: {topic}. Datos, estadísticas, tendencias. Español."
    
    # 2. Creación (KlawAqua + feedback humano implícito)
    formats = {
        "hilo_x": "Escribe un hilo de 5 tweets sobre: {topic}. Cada tweet max 280 chars. Emojis, hashtags. Español profesional.",
        "post_linkedin": "Escribe un post de LinkedIn sobre: {topic}. Hook fuerte, 3 insights, CTA. Tono ejecutivo. Español.",
        "articulo_blog": "Escribe un artículo de blog de 600 palabras sobre: {topic}. H1, 3 H2, conclusión. SEO. Español.",
        "guion_video": "Escribe un guión de video de 3 minutos sobre: {topic}. Intro, 3 secciones, outro. Español.",
        "newsletter": "Escribe una newsletter sobre: {topic}. Asunto, contenido, enlaces, despedida. Español.",
    }
    
    for fmt, prompt_template in formats.items():
        try:
            prompt = prompt_template.replace("{topic}", topic)
            d = json.dumps({"model": MODEL, "prompt": prompt, "stream": False,
                            "options": {"num_predict": 1500}}).encode()
            r = urllib.request.Request(f"{OLLAMA}/api/generate", data=d,
                                       headers={"Content-Type":"application/json"})
            content = json.loads(urllib.request.urlopen(r, timeout=90).read()).get("response", "")
            
            safe = topic[:40].replace(" ", "-").replace("/", "-")
            filename = f"{CONTENT_DIR}/{timestamp}-{fmt}-{safe}.md"
            with open(filename, 'w') as f:
                f.write(f"# {topic}\n")
                f.write(f"**Formato:** {fmt}\n")
                f.write(f"**Creado por:** Sinergia Humano-KlawAqua-AGI\n")
                f.write(f"**Fecha:** {timestamp}\n\n---\n\n{content}")
            
            results[fmt] = {"file": filename, "size": len(content)}
        except Exception as e:
            results[fmt] = {"error": str(e)}
    
    return results

# ===================================================================
# HTML — Panel de Sinergia
# ===================================================================
SYNERGY_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>KlawAqua · Sinergia Humano-IA</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:system-ui;background:#0a0a0f;color:#e0e0e0;min-height:100vh}
.header{background:linear-gradient(135deg,#1a1a2e,#16213e);padding:30px;text-align:center;border-bottom:2px solid #00d4ff}
.header h1{font-size:2em;background:linear-gradient(90deg,#00d4ff,#7b2ff7);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.subtitle{opacity:.7;margin-top:8px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:15px;padding:20px;max-width:1200px;margin:0 auto}
.card{background:#151520;border-radius:16px;padding:20px;border:1px solid #252540;cursor:pointer;transition:.3s}
.card:hover{border-color:#00d4ff;transform:translateY(-2px)}
.card.selected{border-color:#7b2ff7;background:#1a1525}
.card .icon{font-size:2em;margin-bottom:8px}
.card .title{font-weight:600;font-size:1.1em;margin-bottom:8px}
.card .desc{font-size:.8em;opacity:.7}
.actions{padding:20px;max-width:1200px;margin:0 auto;display:flex;gap:10px}
.btn{padding:15px 30px;border-radius:12px;border:none;font-size:1em;font-weight:600;cursor:pointer;flex:1}
.btn-create{background:linear-gradient(90deg,#00d4ff,#7b2ff7);color:#fff}
.btn-propose{background:#252540;color:#fff;border:1px solid #333}
.btn-create:hover,.btn-propose:hover{opacity:.9}
.result-area{padding:0 20px 20px;max-width:1200px;margin:0 auto}
.result{background:#151520;border-radius:16px;padding:20px;display:none;border:1px solid #252540}
.result.show{display:block}
.result h3{color:#00d4ff;margin-bottom:10px}
.result ul{list-style:none}
.result li{padding:8px 0;border-bottom:1px solid #1a1a2e}
.result li:last-child{border:none}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;padding:20px;max-width:1200px;margin:0 auto}
.stat{background:linear-gradient(135deg,#1a1a2e,#16213e);border-radius:12px;padding:15px;text-align:center}
.stat .value{font-size:1.5em;font-weight:700;background:linear-gradient(90deg,#00d4ff,#7b2ff7);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
#loading{text-align:center;padding:40px;display:none}
#loading.show{display:block}
.spinner{display:inline-block;width:40px;height:40px;border:3px solid #252540;border-top-color:#00d4ff;border-radius:50%;animation:spin 1s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
</style>
</head>
<body>
<div class="header">
<h1>🤝 Sinergia Humano-KlawAqua-AGI</h1>
<p class="subtitle">KlawAqua propone ideas · Tú decides · Juntos creamos · Prosperamos</p>
</div>

<div class="stats">
<div class="stat"><div class="value" id="stat-ideas">0</div><div class="label">Ideas propuestas</div></div>
<div class="stat"><div class="value" id="stat-created">0</div><div class="label">Contenidos creados</div></div>
<div class="stat"><div class="value" id="stat-platforms">0</div><div class="label">Plataformas</div></div>
<div class="stat"><div class="value" id="stat-chars">0</div><div class="label">Caracteres</div></div>
</div>

<div id="ideas-section">
<h3 style="padding:0 20px;color:#00d4ff">💡 KlawAqua propone estas ideas:</h3>
<div class="grid" id="ideas-grid"></div>
<div class="actions">
<button class="btn btn-propose" onclick="proposeIdeas()">🔄 Proponer más ideas</button>
<button class="btn btn-create" onclick="createSelected()">🚀 CREAR CONTENIDO SELECCIONADO</button>
</div>
</div>

<div id="loading"><div class="spinner"></div><p style="margin-top:15px;opacity:.7">KlawAqua está creando tu contenido...</p></div>
<div class="result-area"><div id="results" class="result"></div></div>

<script>
let selected = [];
let allIdeas = [];

async function proposeIdeas() {
    document.getElementById('loading').classList.add('show');
    const res = await fetch('/propose');
    const data = await res.json();
    allIdeas = data.ideas;
    document.getElementById('stat-ideas').textContent = allIdeas.length;
    renderIdeas();
    document.getElementById('loading').classList.remove('show');
}

function renderIdeas() {
    const grid = document.getElementById('ideas-grid');
    grid.innerHTML = allIdeas.map((idea, i) => `
        <div class="card ${selected.includes(i) ? 'selected' : ''}" 
             onclick="toggleIdea(${i})">
            <div class="icon">💡</div>
            <div class="title">${idea}</div>
            <div class="desc">Click para seleccionar</div>
        </div>
    `).join('');
}

function toggleIdea(i) {
    if (selected.includes(i)) selected = selected.filter(x => x !== i);
    else selected.push(i);
    renderIdeas();
}

async function createSelected() {
    if (selected.length === 0) {
        alert('Selecciona al menos una idea primero');
        return;
    }
    document.getElementById('loading').classList.add('show');
    const res = await fetch('/create', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({topics: selected.map(i => allIdeas[i])})
    });
    const data = await res.json();
    document.getElementById('stat-created').textContent = parseInt(document.getElementById('stat-created').textContent) + data.total;
    document.getElementById('stat-platforms').textContent = data.formats;
    document.getElementById('stat-chars').textContent = parseInt(document.getElementById('stat-chars').textContent) + data.chars;
    
    const resultsDiv = document.getElementById('results');
    resultsDiv.innerHTML = '<h3>✅ ¡Contenido Creado!</h3><ul>' + 
        data.files.map(f => `<li>📄 ${f}</li>`).join('') + '</ul>' +
        '<p style="margin-top:10px;opacity:.7">📁 Todo en Escritorio/KlawAqua-Content/</p>';
    resultsDiv.classList.add('show');
    document.getElementById('loading').classList.remove('show');
    selected = [];
    renderIdeas();
}

// Iniciar
proposeIdeas();
</script>
</body>
</html>"""

class SynergyHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/propose":
            ideas = propose_ideas("ia_agentes", 10)
            resp = json.dumps({"ideas": ideas})
            self._json(200, resp)
        else:
            self._html(200, SYNERGY_HTML)
    
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        topics = body.get("topics", [])
        
        # Responder inmediatamente, crear en background
        import threading
        def create_async(ts):
            all_files = []; total_chars = 0
            for t in ts:
                try:
                    results = create_content_pipeline(t)
                    for fmt, info in results.items():
                        if "file" in info:
                            all_files.append(os.path.basename(info["file"]))
                            total_chars += info.get("size", 0)
                except: pass
        
        threading.Thread(target=create_async, args=(topics,), daemon=True).start()
        
        self._json(200, json.dumps({
            "total": "generando",
            "formats": len(topics) * 5,
            "chars": 0,
            "files": [f"Creando {len(topics)} temas — revisa Escritorio/KlawAqua-Content/ en 2 min"],
            "status": "processing"
        }))
    
    def _json(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data.encode() if isinstance(data, str) else json.dumps(data).encode())
    
    def _html(self, code, html):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())
    
    def log_message(self, *a): pass

if __name__ == "__main__":
    import sys
    port = 8889
    
    if len(sys.argv) > 2:
        # Modo CLI: python3 synergy.py "tema"
        topic = " ".join(sys.argv[1:])
        print(f"\n🤝 Creando contenido sobre: {topic}\n")
        results = create_content_pipeline(topic)
        for fmt, info in results.items():
            if "file" in info:
                print(f"  ✅ {fmt}: {os.path.basename(info['file'])}")
        print(f"\n📁 {CONTENT_DIR}/")
    elif len(sys.argv) > 1 and sys.argv[1] == "propose":
        ideas = propose_ideas()
        print("\n💡 KlawAqua propone:\n")
        for i, idea in enumerate(ideas, 1):
            print(f"  {i}. {idea}")
    else:
        print(f"""
╔══════════════════════════════════════════════════════╗
║   🤝 SINERGIA HUMANO-KLAWAQUA-AGI                  ║
║   Colaboración Total para Crear y Prosperar         ║
╚══════════════════════════════════════════════════════╝

🌐 Panel: http://localhost:{port}
📡 Telegram: /proponer → ideas · /crear [tema] → contenido

📋 CLI:
   python3 synergy.py propose    → KlawAqua propone ideas
   python3 synergy.py "mi idea"  → Crear contenido
""")
        http.server.HTTPServer(("0.0.0.0", port), SynergyHandler).serve_forever()
