"""Generate the static One Piece birthday API from data/birthdays.json.

Run from this folder:  python build.py
Writes v1/ (JSON endpoints) next to index.html. Uses the standard library only.
"""

import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "data" / "birthdays.json"
OUT = ROOT / "v1"

MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
MONTH_DAYS = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
LABEL_RE = re.compile(r"^(%s) (\d{1,2})(?:st|nd|rd|th)" % "|".join(MONTHS))


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def parse_label(label: str) -> tuple[int, int]:
    match = LABEL_RE.match(label)
    if not match:
        raise ValueError(f"Unrecognised date label: {label!r}")
    return MONTHS.index(match.group(1)) + 1, int(match.group(2))


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    raw = json.loads(SOURCE.read_text(encoding="utf-8"))

    entries = {}
    for label, names in raw.items():
        month, day = parse_label(label)
        if not 1 <= day <= MONTH_DAYS[month - 1]:
            raise ValueError(f"Invalid day in label: {label!r}")
        key = f"{month:02d}-{day:02d}"
        if key in entries:
            raise ValueError(f"Duplicate date: {label!r}")
        entries[key] = {
            "date": key,
            "label": label,
            "month": month,
            "day": day,
            "characters": [n.strip() for n in names if n.strip()],
        }

    # Every calendar day gets a file, even if the source has no one for it.
    days = []
    for month, count in enumerate(MONTH_DAYS, start=1):
        for day in range(1, count + 1):
            key = f"{month:02d}-{day:02d}"
            days.append(entries.get(key) or {
                "date": key,
                "label": f"{MONTHS[month - 1]} {day}",
                "month": month,
                "day": day,
                "characters": [],
            })

    if OUT.exists():
        shutil.rmtree(OUT)

    for entry in days:
        write_json(OUT / "dates" / f"{entry['date']}.json", entry)

    for month in range(1, 13):
        month_days = [e for e in days if e["month"] == month]
        write_json(OUT / "months" / f"{month:02d}.json", {
            "month": month,
            "name": MONTHS[month - 1],
            "count": sum(len(e["characters"]) for e in month_days),
            "days": month_days,
        })

    characters = {}
    for entry in days:
        for name in entry["characters"]:
            record = characters.setdefault(name, {"name": name, "slug": slugify(name), "dates": []})
            record["dates"].append(entry["date"])
    character_list = sorted(characters.values(), key=lambda c: c["name"].lower())

    total = sum(len(e["characters"]) for e in days)
    write_json(OUT / "all.json", {"count": total, "days": days})
    write_json(OUT / "characters.json", {"count": len(character_list), "characters": character_list})
    write_json(OUT / "index.json", {
        "name": "One Piece Birthday API",
        "version": 1,
        "characters": len(character_list),
        "entries": total,
        "endpoints": {
            "date": "v1/dates/{MM}-{DD}.json",
            "month": "v1/months/{MM}.json",
            "all": "v1/all.json",
            "characters": "v1/characters.json",
        },
    })

    print(f"Wrote {len(days)} dates, 12 months, {len(character_list)} characters ({total} entries) to {OUT}")


if __name__ == "__main__":
    main()
