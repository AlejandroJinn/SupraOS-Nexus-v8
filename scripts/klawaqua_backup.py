#!/usr/bin/env python3
"""
KlawAqua Smart Backup — FASE 2
Sincroniza proyectos, modelos y datos del sistema al SSD USB 2TB
Estrategia: activos -> caliente (NVMe), inactivos -> frio (USB SSD)
"""
import os, subprocess, json, time, datetime
from pathlib import Path

USB_SSD = "/run/media/clarwis/SSD"
BACKUP_DIR = f"{USB_SSD}/klawaqua-backups"
ARCHIVE_DIR = f"{USB_SSD}/klawaqua-archive"
MODELS_USB = f"{USB_SSD}/klawaqua-models"
HOT_DIRS = ["/opt/klawaqua/scripts", "/opt/klawaqua/dashboard", "/opt/klawaqua/data"]
PROJECTS_DIR = "/opt/klawaqua/projects"

def ensure_dirs():
    for d in [BACKUP_DIR, ARCHIVE_DIR, MODELS_USB]:
        Path(d).mkdir(parents=True, exist_ok=True)

def get_projects_activity():
    """Detecta repos activos (commits ultimos 30 dias) vs inactivos"""
    now = time.time()
    cutoff = now - 30*86400
    active, inactive = [], []
    pdir = Path(PROJECTS_DIR)
    if not pdir.exists(): return [], []
    for proj in pdir.iterdir():
        if not proj.is_dir() or proj.name.startswith("."):
            continue
        git_dir = proj / ".git"
        if git_dir.exists():
            try:
                mtime = os.path.getmtime(str(git_dir / "HEAD"))
                if mtime > cutoff:
                    active.append(proj.name)
                else:
                    inactive.append(proj.name)
            except:
                inactive.append(proj.name)
        else:
            inactive.append(proj.name)
    return active, inactive

def rsync(src, dst, excludes=None, dry=False):
    cmd = ["rsync", "-avh", "--delete", "--progress"]
    if excludes:
        for e in excludes:
            cmd.extend(["--exclude", e])
    if dry:
        cmd.append("--dry-run")
    cmd.extend([src + "/", dst + "/"])
    print(f"[BACKUP] {'(dry)' if dry else ''} {src} -> {dst}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0, result.stdout, result.stderr

def backup_hot_dirs():
    """Backup de scripts, dashboard, data al USB SSD"""
    print("=== BACKUP HOT DIRS ===")
    for src in HOT_DIRS:
        name = Path(src).name
        dst = f"{BACKUP_DIR}/{name}"
        Path(dst).mkdir(parents=True, exist_ok=True)
        ok, out, err = rsync(src, dst)
        print(f"{'✅' if ok else '❌'} {name}: {out.splitlines()[-1] if out else 'ok'}")

def archive_inactive_projects(inactive):
    """Mueve repos inactivos al SSD USB (cold storage)"""
    print("\n=== ARCHIVE INACTIVE ===")
    archived = []
    for name in inactive:
        src = f"{PROJECTS_DIR}/{name}"
        dst = f"{ARCHIVE_DIR}/{name}"
        if Path(dst).exists():
            print(f"⚠️ {name} ya archivado, saltando")
            continue
        print(f"📦 Archivando: {name} -> {ARCHIVE_DIR}")
        subprocess.run(["cp", "-r", src, dst], check=False)
        # Dejar un .archive-moved marker
        with open(f"{src}/.archived", "w") as f:
            f.write(f"Archived to: {dst}\nDate: {datetime.datetime.now().isoformat()}\nRestore: cp -r {dst} {src}")
        archived.append(name)
    print(f"Archivados: {len(archived)} proyectos")
    return archived

def mirror_models():
    """Mirror GGUF models al USB SSD y crear symlinks"""
    print("\n=== MODELS MIRROR ===")
    model_dirs = ["/opt/klawaqua/models/gguf", "/opt/klawaqua/models/minicpm"]
    for src in model_dirs:
        if not Path(src).exists():
            continue
        name = Path(src).name
        dst = f"{MODELS_USB}/{name}"
        Path(dst).mkdir(parents=True, exist_ok=True)
        ok, out, err = rsync(src, dst, excludes=["*.tmp", "*.part"])
        print(f"{'✅' if ok else '❌'} {name}")

def generate_report():
    """Genera resumen del backup"""
    active, inactive = get_projects_activity()
    now = datetime.datetime.now().isoformat()
    report = {
        "ts": now,
        "active_projects": len(active),
        "inactive_projects": len(inactive),
        "usb_ssd_usage": _get_usage(USB_SSD),
        "backup_dir": BACKUP_DIR,
        "archive_dir": ARCHIVE_DIR,
        "models_dir": MODELS_USB,
    }
    repath = f"{BACKUP_DIR}/report.json"
    with open(repath, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n📊 Reporte guardado: {repath}")
    return report

def _get_usage(path):
    try:
        r = subprocess.check_output(["df", "-h", path]).decode().split("\n")[1]
        parts = r.split()
        return {"size": parts[1], "used": parts[2], "available": parts[3], "pct": parts[4]}
    except Exception as e:
        return {"error": str(e)}

# ─── CLI ────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="KlawAqua Smart Backup")
    parser.add_argument("command", choices=["backup", "report", "archive", "mirror", "all"])
    parser.add_argument("--dry", action="store_true", help="Simular sin ejecutar")
    args = parser.parse_args()
    
    ensure_dirs()
    
    if args.command == "backup":
        backup_hot_dirs()
    elif args.command == "archive":
        active, inactive = get_projects_activity()
        archive_inactive_projects(inactive)
    elif args.command == "mirror":
        mirror_models()
    elif args.command == "report":
        print(json.dumps(generate_report(), indent=2))
    elif args.command == "all":
        backup_hot_dirs()
        mirror_models()
        active, inactive = get_projects_activity()
        archive_inactive_projects(inactive)
        generate_report()
        print("\n🌊 Backup completo. Fluye como el agua.")
