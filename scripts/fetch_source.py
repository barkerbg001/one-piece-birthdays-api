"""Scrape The Library of Ohara birthday calendar into data/source.json.

    python scripts/fetch_source.py

The page lists each month as "1st – Name, Name, [Sibling A, Sibling B]".
Square brackets group characters who share a birthday by birth (siblings,
twins). Parentheses hold either an alias ("Daz Bones (Mr. 1)") or an editor's
note ("Giolla (previously stated to be 27th ..., later retconned to 25th)").
Commas inside brackets or parentheses never split a name.
"""

import html
import json
import re
import sys
from datetime import date
from pathlib import Path

import urllib.request

SOURCE_URL = "https://thelibraryofohara.com/birthday-calendar/"
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "source.json"

MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
NOTE_WORDS = 5  # parentheses with this many words or more are notes, not aliases


def download(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "one-piece-birthdays-api/1.0"})
    with urllib.request.urlopen(req, timeout=30) as res:
        return res.read().decode("utf-8", errors="replace")


def split_top_level(text: str) -> list[tuple[str, int | None]]:
    """Split on commas outside () and []. Returns (item, bracket_group_index)."""
    items, buf, paren, group, group_id, next_group = [], "", 0, False, None, 0
    for ch in text:
        if ch == "(":
            paren += 1
        elif ch == ")":
            paren = max(0, paren - 1)
        elif ch == "[" and paren == 0:
            group, group_id = True, next_group
            next_group += 1
            continue
        elif ch == "]" and paren == 0:
            items.append((buf, group_id))
            buf, group = "", False
            continue
        if ch == "," and paren == 0:
            items.append((buf, group_id if group else None))
            buf = ""
            continue
        buf += ch
    items.append((buf, group_id if group else None))
    return [(item.strip(), gid) for item, gid in items if item.strip()]


def parse_entry(raw: str) -> dict:
    match = re.match(r"^(.*?)\s*\((.*)\)\s*$", raw)
    name, paren = (match.group(1), match.group(2).strip()) if match else (raw, None)
    entry = {"name": name.strip(), "alias": None, "note": None, "source_text": raw}
    if paren:
        if len(paren.split()) >= NOTE_WORDS:
            entry["note"] = paren
        else:
            entry["alias"] = paren
    return entry


def parse(page: str) -> dict:
    days = {}
    pattern = re.compile(r"<strong>(%s)</strong>(.*?)</p>" % "|".join(MONTHS), re.S)
    for block in pattern.finditer(page):
        month = MONTHS.index(block.group(1)) + 1
        for line in re.split(r"<br\s*/?>", block.group(2)):
            line = html.unescape(re.sub(r"<[^>]+>", "", line)).strip()
            if not line:
                continue
            m = re.match(r"^(\d{1,2})(?:st|nd|rd|th)\s*(?:\(Leap Day\))?\s*[–—-]\s*(.*)$", line)
            if not m:
                raise ValueError(f"Could not parse line in {MONTHS[month - 1]}: {line!r}")
            key = f"{month:02d}-{int(m.group(1)):02d}"
            entries = []
            for raw, gid in split_top_level(m.group(2)):
                entry = parse_entry(raw)
                entry["group"] = f"{key}-{gid}" if gid is not None else None
                entries.append(entry)
            days[key] = entries
    return days


def calendar_images(page: str) -> dict:
    """The page's illustrated month calendars, keyed by "01".."12"."""
    images = {}
    for url in re.findall(r'data-orig-file="([^"]+)"', page):
        url = html.unescape(url)
        filename = url.split("?")[0].rsplit("/", 1)[-1].lower()
        for i, month in enumerate(MONTHS, start=1):
            if filename.startswith(month.lower()):
                size = re.search(r"fit=(\d+)%2C(\d+)", url)
                images.setdefault(f"{i:02d}", {
                    "url": url.split("?")[0],
                    "width": int(size.group(1)) if size else None,
                    "height": int(size.group(2)) if size else None,
                })
    return dict(sorted(images.items()))


def main() -> None:
    page = download(SOURCE_URL)
    days = parse(page)
    images = calendar_images(page)
    if len(days) != 366:
        sys.exit(f"Expected 366 days, parsed {len(days)}. The page layout may have changed.")
    total = sum(len(v) for v in days.values())
    OUT.write_text(json.dumps({
        "source": SOURCE_URL,
        "fetched": date.today().isoformat(),
        "calendar_images": images,
        "days": dict(sorted(days.items())),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Parsed {len(days)} days, {total} entries -> {OUT}")


if __name__ == "__main__":
    main()
