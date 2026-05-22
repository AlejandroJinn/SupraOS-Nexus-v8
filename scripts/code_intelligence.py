#!/usr/bin/env python3
"""
KlawAqua Code Intelligence Scanner v1
1. LOC por proyecto y lenguaje
2. Ratio codigo/comentarios
3. Mapa de dependencias
4. Deteccion de secrets expuestos
5. Index en JSON
"""
import os, json, subprocess, re, hashlib
from pathlib import Path
from collections import defaultdict

PROJECTS = "/opt/klawaqua/projects"
REPORT = "/opt/klawaqua/data/code_intelligence_report.json"
SECRET_PATTERNS = [
    r'(api[_-]?key|apikey)\s*[:=]\s*["\']?[a-zA-Z0-9_-]{20,}["\']?',
    r'(token|secret|password)\s*[:=]\s*["\']?[a-zA-Z0-9_-]{20,}["\']?',
    r'sk-[a-zA-Z0-9]{20,}',
    r'ghp_[a-zA-Z0-9]{20,}',
    r'Bearer\s+[a-zA-Z0-9_-]{20,}',
    r'AKIA[0-9A-Z]{16}',
]
EXCLUDE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".pytest_cache"}

def run_pygount(path):
    try:
        r = subprocess.run(["pygount", "--format", "summary", str(path)], capture_output=True, text=True, timeout=60)
        out = r.stdout
        total, code, comment = 0, 0, 0
        for line in out.split("\n"):
            if line.startswith("Total"):
                parts = line.split()
                if len(parts) >= 4:
                    total = int(parts[1].replace(",",""))
                    code = int(parts[2].replace(",",""))
                    comment = int(parts[3].replace(",",""))
                    break
        return {"total_lines": total, "code_lines": code, "comment_lines": comment}
    except Exception as e:
        return {"error": str(e)}

def detect_languages(path):
    langs = defaultdict(int)
    for root, dirs, files in os.walk(str(path)):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for f in files:
            ext = Path(f).suffix
            if ext:
                langs[ext] += 1
    return dict(sorted(langs.items(), key=lambda x: -x[1])[:10])

def parse_dependencies(path):
    deps = {}
    # Python
    req = Path(path) / "requirements.txt"
    if req.exists():
        deps["python"] = [l.split("==")[0].strip() for l in req.read_text().split("\n") if l.strip() and not l.startswith("#")][:20]
    # Node
    pkg = Path(path) / "package.json"
    if pkg.exists():
        try:
            j = json.loads(pkg.read_text())
            deps["node"] = list(j.get("dependencies", {}).keys())[:20]
            deps["node_dev"] = list(j.get("devDependencies", {}).keys())[:10]
        except: pass
    # Cargo
    cargo = Path(path) / "Cargo.toml"
    if cargo.exists():
        deps["rust"] = re.findall(r'^(\w+)\s*=', cargo.read_text(), re.MULTILINE)[:20]
    # Go
    go = Path(path) / "go.mod"
    if go.exists():
        deps["go"] = re.findall(r'\s(\S+)\s+v[\d.]+', go.read_text())[:20]
    return deps

def scan_secrets(path):
    found = []
    for root, dirs, files in os.walk(str(path)):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for f in files[:500]:  # Limitar archivos
            if f.endswith((".txt", ".py", ".js", ".ts", ".env", ".json", ".yaml", ".yml", ".toml", ".md")):
                fp = Path(root) / f
                try:
                    content = fp.read_text(errors="replace")[:20000]  # Limitar tamaño
                    for pat in SECRET_PATTERNS:
                        for m in re.finditer(pat, content, re.IGNORECASE):
                            found.append({
                                "file": str(fp.relative_to(path)),
                                "line": content[:m.start()].count("\n") + 1,
                                "snippet": content[m.start():m.start()+40],
                                "hash": hashlib.sha256(m.group().encode()).hexdigest()[:12]
                            })
                except: pass
    # Deduplicar por hash
    seen = set()
    unique = []
    for f in found:
        if f["hash"] not in seen:
            seen.add(f["hash"]); unique.append(f)
    return unique[:50]

def scan_all():
    results = {"timestamp": None, "projects": [], "summary": {}}
    pdir = Path(PROJECTS)
    if not pdir.exists(): return results
    
    projects = [d for d in pdir.iterdir() if d.is_dir() and not d.name.startswith(".")]
    print(f"Escaneando {len(projects)} proyectos...")
    
    langs_all = defaultdict(int)
    deps_all = defaultdict(list)
    all_secrets = []
    
    for proj in sorted(projects)[:200]:
        print(f"  [{proj.name}]")
        loc = run_pygount(proj)
        langs = detect_languages(proj)
        deps = parse_dependencies(proj)
        secrets = scan_secrets(proj)
        
        for l, c in langs.items(): langs_all[l] += c
        for k, v in deps.items(): deps_all[k].extend(v)
        all_secrets.extend(secrets)
        
        results["projects"].append({
            "name": proj.name,
            "loc": loc,
            "languages": langs,
            "dependencies": deps,
            "secrets_found": len(secrets),
            "top_secret": secrets[0] if secrets else None
        })
    
    results["summary"] = {
        "total_projects": len(projects),
        "languages": dict(sorted(langs_all.items(), key=lambda x: -x[1])[:20]),
        "total_secrets": len(all_secrets),
        "secrets_unique_hashes": len(set(s["hash"] for s in all_secrets)),
        "dependency_files": {k: len(set(v)) for k, v in deps_all.items()},
    }
    results["timestamp"] = __import__("datetime").datetime.now().isoformat()
    
    with open(REPORT, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nReporte guardado: {REPORT}")
    print(f"Proyectos: {results['summary']['total_projects']}")
    print(f"Secrets: {results['summary']['total_secrets']}")
    return results

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--scan", action="store_true")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()
    
    if args.scan:
        scan_all()
    elif args.summary:
        with open(REPORT) as f:
            r = json.load(f)
        print(f"Proyectos: {r['summary']['total_projects']}")
        print(f"Lenguajes: {r['summary']['languages']}")
        print(f"Secrets: {r['summary']['total_secrets']}")
        if r['summary']['total_secrets'] > 0:
            print("⚠️ REVISAR SECRETS EXPUESTOS")
    else:
        print("Uso: code_intelligence.py --scan | --summary")
