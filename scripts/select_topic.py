import json
from pathlib import Path
from datetime import date

DB_PATH = Path("data/topic_db.json")

def select_topic():
    db = json.loads(DB_PATH.read_text(encoding="utf-8"))

    recent = db.get("recent_reports", [])
    last_categories = [r["main_category"] for r in recent[-5:]]

    candidates = db.get("candidate_pool", [])

    scored = []
    for c in candidates:
        score = c.get("priority", 0.5)

        if c["main_category"] == last_categories[-1]:
            score -= 0.5

        if c["main_category"] in last_categories[-3:]:
            score -= 0.2

        if c.get("status") == "used":
            score -= 1.0

        scored.append((score, c))

    scored.sort(reverse=True, key=lambda x: x[0])
    selected = scored[0][1]

    selected["selected_date"] = str(date.today())
    return selected