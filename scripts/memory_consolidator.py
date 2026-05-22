#!/usr/bin/env python3
"""
KlawAqua Memory Consolidator v1 — FASE 4
Resumen semanal de conversaciones + olvido selectivo KAIYA
"""
import sqlite3, json, os, datetime
from pathlib import Path

KAIYA_DB = "/opt/klawaqua/data/kaiya_soul.db"
SUMMARY_DAYS = 7
FORGET_DAYS = 30
FORGET_IMPORTANCE = 30
ARCHIVE_DB = "/opt/klawaqua/data/kaiya_archive.db"

def _init():
    Path(ARCHIVE_DB).parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(ARCHIVE_DB)
    c.execute("""
        CREATE TABLE IF NOT EXISTS weekly_summaries (
            id INTEGER PRIMARY KEY,
            week_start TEXT,
            week_end TEXT,
            topics TEXT,
            key_decisions TEXT,
            emotional_avg TEXT,
            total_interactions INTEGER
        )
    """)
    c.commit(); c.close()

def get_week_interactions():
    """Obtiene conversaciones ultimos 7 dias"""
    c = sqlite3.connect(KAIYA_DB)
    cutoff = (datetime.datetime.now() - datetime.timedelta(days=SUMMARY_DAYS)).isoformat()
    rows = c.execute("""
        SELECT role, content, emotion_energy, emotion_valence, ts 
        FROM kaiya_chat 
        WHERE ts > ? ORDER BY id ASC
    """, (cutoff,)).fetchall()
    c.close()
    return [{"role": r[0], "content": r[1], "energy": r[2], "valence": r[3], "ts": r[4]} for r in rows]

def generate_summary(interactions):
    if not interactions:
        return None
    
    topics = set()
    for i in interactions:
        c = i["content"].lower()
        if "codigo" in c or "python" in c or "script" in c: topics.add("codigo")
        if_backup = any(k in c for k in ["backup", "copiar", "rsync", "guardar"])
        if if_backup: topics.add("backup")
        if "nexus" in c: topics.add("nexus")
        if "router" in c: topics.add("router")
        if "modelo" in c or "llama" in c: topics.add("ml/gpu")
        if "kawaqua" in c or "ecosistema" in c: topics.add("ecosistema")
    
    user_msgs = [i for i in interactions if i["role"] == "user"]
    ai_msgs = [i for i in interactions if i["role"] == "ai"]
    
    avg_energy = sum(i["energy"] for i in ai_msgs) / len(ai_msgs) if ai_msgs else 0.5
    avg_valence = sum(i["valence"] for i in ai_msgs) / len(ai_msgs) if ai_msgs else 0.5
    
    summary = {
        "week_start": interactions[0]["ts"][:10],
        "week_end": interactions[-1]["ts"][:10],
        "topics": list(topics),
        "key_decisions": f"{len(interactions)} interacciones, {len(user_msgs)} del usuario, {len(ai_msgs)} de KAIYA",
        "emotional_avg": {"energy": round(avg_energy, 2), "valence": round(avg_valence, 2)},
        "total_interactions": len(interactions)
    }
    return summary

def archive_summary(summary):
    c = sqlite3.connect(ARCHIVE_DB)
    c.execute("""
        INSERT INTO weekly_summaries(week_start, week_end, topics, key_decisions, emotional_avg, total_interactions)
        VALUES(?,?,?,?,?,?)
    """, (summary["week_start"], summary["week_end"], json.dumps(summary["topics"]),
          summary["key_decisions"], json.dumps(summary["emotional_avg"]), summary["total_interactions"]))
    c.commit(); c.close()
    return True

def forget_old_memories():
    """Borra interacciones antiguas con importancia baja"""
    # Como no hay campo importance, usamos una euristica: borra las mas viejas
    c = sqlite3.connect(KAIYA_DB)
    cutoff = (datetime.datetime.now() - datetime.timedelta(days=FORGET_DAYS)).isoformat()
    
    # Contar antes
    total_before = c.execute("SELECT COUNT(*) FROM kaiya_chat").fetchone()[0]
    
    # Borrar interacciones antiguas (mas de 30 dias)
    c.execute("DELETE FROM kaiya_chat WHERE ts < ?", (cutoff,))
    deleted = c.rowcount
    
    # Vacuum para compactar
    c.execute("VACUUM")
    c.commit()
    
    total_after = c.execute("SELECT COUNT(*) FROM kaiya_chat").fetchone()[0]
    c.close()
    
    return {"before": total_before, "deleted": deleted, "after": total_after}

def get_all_summaries():
    c = sqlite3.connect(ARCHIVE_DB)
    rows = c.execute("SELECT * FROM weekly_summaries ORDER BY id DESC LIMIT 20").fetchall()
    c.close()
    return [{
        "id": r[0], "week_start": r[1], "week_end": r[2],
        "topics": json.loads(r[3]), "key_decisions": r[4],
        "emotional_avg": json.loads(r[5]), "total": r[6]
    } for r in rows]

# ─── CLI ────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["summary", "forget", "archive", "status"])
    args = parser.parse_args()
    
    _init()
    
    if args.command == "summary":
        interactions = get_week_interactions()
        s = generate_summary(interactions)
        print(json.dumps(s, indent=2, default=str))
    elif args.command == "archive":
        interactions = get_week_interactions()
        s = generate_summary(interactions)
        if s: archive_summary(s); print("Archivado.")
        else: print("Sin datos.")
    elif args.command == "forget":
        r = forget_old_memories()
        print(f"Antes: {r['before']}, Borrados: {r['deleted']}, Despues: {r['after']}")
    elif args.command == "status":
        print("Summaries archivadas:", len(get_all_summaries()))
        import sqlite3
        c = sqlite3.connect(KAIYA_DB)
        total = c.execute("SELECT COUNT(*) FROM kaiya_chat").fetchone()[0]
        c.close()
        print(f"Memorias KAIYA: {total}")
