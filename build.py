"""Generate the static One Piece birthday API.

    python build.py

Inputs (see scripts/ for how they're produced):
  data/source.json  birthdays scraped from The Library of Ohara
  data/wiki.json    One Piece Wiki matches: page, image links, infobox facts

Writes v1/ next to index.html. Standard library only, no network.
"""

import json
import re
import shutil
import unicodedata
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "data" / "source.json"
WIKI = ROOT / "data" / "wiki.json"
OUT = ROOT / "v1"

MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
MONTH_DAYS = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

SOURCES = {
    "birthdays": {
        "name": "The Library of Ohara – One Piece Birthday Calendar",
        "url": "https://thelibraryofohara.com/birthday-calendar/",
    },
    "character_info": {
        "name": "One Piece Wiki (Fandom)",
        "url": "https://onepiece.fandom.com/",
        "license": "CC BY-SA 3.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/3.0/",
    },
    "images": "Character images are links to the One Piece Wiki's image CDN and are © Eiichiro Oda / Shueisha / Toei Animation. They are not hosted here.",
}


def ordinal(day: int) -> str:
    if 11 <= day % 100 <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")


def label(month: int, day: int) -> str:
    if (month, day) == (2, 29):
        return "February 29th (Leap Day)"
    return f"{MONTHS[month - 1]} {day}{ordinal(day)}"


def slugify(name: str) -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "character"


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    wiki = json.loads(WIKI.read_text(encoding="utf-8")) if WIKI.exists() else {}
    days_src = source["days"]
    calendar_images = source.get("calendar_images", {})

    # ---- characters, keyed by source name
    characters: dict[str, dict] = {}
    used_slugs: set[str] = set()
    for key in sorted(days_src):
        for entry in days_src[key]:
            name = entry["name"]
            if name not in characters:
                slug = base = slugify(name)
                n = 2
                while slug in used_slugs:
                    slug, n = f"{base}-{n}", n + 1
                used_slugs.add(slug)
                w = wiki.get(name)
                characters[name] = {
                    "id": slug,
                    "name": name,
                    "display_name": f"{name} ({entry['alias']})" if entry.get("alias") else name,
                    "alias": entry.get("alias"),
                    "note": entry.get("note"),
                    "birthdays": [],
                    "born_with": [],
                    "image": w["image"] if w else None,
                    "thumbnail": w["thumbnail"] if w else None,
                    "wiki": {"title": w["title"], "url": w["url"]} if w else None,
                    "info": w["info"] if w else {},
                }
            month, day = int(key[:2]), int(key[3:])
            characters[name]["birthdays"].append({"date": key, "label": label(month, day)})

    # ---- born_with: others in the same [bracket group] on the same day
    for entries in days_src.values():
        groups: dict[str, list[str]] = {}
        for e in entries:
            if e.get("group"):
                groups.setdefault(e["group"], []).append(e["name"])
        for members in groups.values():
            for name in members:
                for other in members:
                    ref = {"id": characters[other]["id"], "name": other}
                    if other != name and ref not in characters[name]["born_with"]:
                        characters[name]["born_with"].append(ref)

    def summary(c: dict) -> dict:
        """Compact form used inside date/month/all listings."""
        return {
            "id": c["id"],
            "name": c["name"],
            "display_name": c["display_name"],
            "alias": c["alias"],
            "note": c["note"],
            "born_with": [b["id"] for b in c["born_with"]],
            "thumbnail": c["thumbnail"]["url"] if c["thumbnail"] else None,
            "image": c["image"]["url"] if c["image"] else None,
            "wiki_url": c["wiki"]["url"] if c["wiki"] else None,
            "epithet": c["info"].get("epithet"),
            "affiliation": (c["info"].get("affiliations") or [None])[0],
            "api": f"v1/characters/{c['id']}.json",
        }

    # ---- days
    days = []
    for month, count in enumerate(MONTH_DAYS, start=1):
        for day in range(1, count + 1):
            key = f"{month:02d}-{day:02d}"
            chars = [characters[e["name"]] for e in days_src.get(key, [])]
            days.append({
                "date": key,
                "label": label(month, day),
                "month": month,
                "day": day,
                "names": [c["display_name"] for c in chars],
                "characters": [summary(c) for c in chars],
            })

    if OUT.exists():
        shutil.rmtree(OUT)

    for d in days:
        write_json(OUT / "dates" / f"{d['date']}.json", d)

    for month in range(1, 13):
        month_days = [d for d in days if d["month"] == month]
        write_json(OUT / "months" / f"{month:02d}.json", {
            "month": month,
            "name": MONTHS[month - 1],
            "count": sum(len(d["characters"]) for d in month_days),
            "calendar_image": calendar_images.get(f"{month:02d}"),
            "days": month_days,
        })

    char_list = sorted(characters.values(), key=lambda c: c["name"].lower())
    for c in char_list:
        write_json(OUT / "characters" / f"{c['id']}.json", {**c, "sources": SOURCES})

    total = sum(len(d["characters"]) for d in days)
    with_images = sum(1 for c in char_list if c["image"])
    write_json(OUT / "all.json", {"count": total, "days": days})
    write_json(OUT / "characters.json", {
        "count": len(char_list),
        "characters": [
            {**summary(c), "birthdays": [b["date"] for b in c["birthdays"]]}
            for c in char_list
        ],
    })
    write_json(OUT / "index.json", {
        "name": "One Piece Birthday API",
        "version": 1,
        "built": date.today().isoformat(),
        "source_fetched": source.get("fetched"),
        "characters": len(char_list),
        "entries": total,
        "with_images": with_images,
        "endpoints": {
            "date": "v1/dates/{MM}-{DD}.json",
            "month": "v1/months/{MM}.json",
            "character": "v1/characters/{id}.json",
            "characters": "v1/characters.json",
            "all": "v1/all.json",
        },
        "sources": SOURCES,
    })

    print(f"Wrote {len(days)} dates, 12 months, {len(char_list)} characters "
          f"({total} entries, {with_images} with images) to {OUT}")


if __name__ == "__main__":
    main()
