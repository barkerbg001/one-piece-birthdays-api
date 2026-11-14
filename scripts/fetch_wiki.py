"""Match each character to the One Piece Wiki and pull image + infobox data.

    python scripts/fetch_wiki.py            # use cached wiki responses where present
    python scripts/fetch_wiki.py --refresh  # re-download everything

Reads data/source.json and data/wiki_overrides.json, writes data/wiki.json.
Raw API responses are cached in .cache/ (git-ignored) so reruns are cheap.

Images are not copied: wiki.json stores links to the wiki's own image CDN.
Infobox text from the wiki is CC BY-SA; see README for attribution.
"""

import hashlib
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://onepiece.fandom.com/api.php"
WIKI = "https://onepiece.fandom.com/wiki/"
ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "data" / "source.json"
OVERRIDES = ROOT / "data" / "wiki_overrides.json"
OUT = ROOT / "data" / "wiki.json"
CACHE = ROOT / ".cache" / "wiki"
USER_AGENT = "one-piece-birthdays-api/1.0 (static birthday dataset)"
BATCH = 50
DELAY = 1.0  # seconds between live requests

REFRESH = "--refresh" in sys.argv

# Infobox field -> output key. Only fields worth exposing in the API.
FIELDS = {
    "jname": "japanese_name",
    "rname": "romanized_name",
    "ename": "official_english_name",
    "first": "debut",
    "affiliation": "affiliations",
    "occupation": "occupations",
    "origin": "origin",
    "residence": "residence",
    "epithet": "epithet",
    "alias": "aliases",
    "status": "status",
    "age": "age",
    "birth": "birthday",
    "height": "height",
    "blood type": "blood_type",
    "bounty": "bounty",
    "dfname": "devil_fruit",
    "dfename": "devil_fruit_english",
    "dftype": "devil_fruit_type",
}
LIST_FIELDS = {"affiliations", "occupations", "aliases", "debut", "residence"}
# Any "{{Char Box", "{{Ship Box", "{{Animal Box" ... style infobox.
INFOBOX_RE = re.compile(r"\{\{\s*([A-Z][\w ]*? Box)\s*(?:\||\n)")


# --------------------------------------------------------------------- HTTP

def api_get(params: dict) -> dict:
    params = {"format": "json", "formatversion": "2", **params}
    query = urllib.parse.urlencode(params)
    key = hashlib.sha1(query.encode()).hexdigest()
    cached = CACHE / f"{key}.json"
    if cached.exists() and not REFRESH:
        return json.loads(cached.read_text(encoding="utf-8"))
    req = urllib.request.Request(f"{API}?{query}", headers={"User-Agent": USER_AGENT})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                data = json.loads(res.read().decode("utf-8"))
            break
        except Exception as exc:  # network blips, 429s
            if attempt == 3:
                raise
            print(f"  retry after error: {exc}")
            time.sleep(5 * (attempt + 1))
    CACHE.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    time.sleep(DELAY)
    return data


def fetch_pages(titles: list[str]) -> dict[str, dict]:
    """Resolve titles (following redirects) -> {requested title: page dict or None}."""
    result = {}
    for i in range(0, len(titles), BATCH):
        chunk = titles[i:i + BATCH]
        data = api_get({
            "action": "query",
            "redirects": "1",
            "prop": "pageimages|revisions|info",
            "piprop": "thumbnail|original|name",
            "pithumbsize": "400",
            "rvprop": "content",
            "rvslots": "main",
            "inprop": "url",
            "titles": "|".join(chunk),
        })
        q = data.get("query", {})
        alias = {t: t for t in chunk}
        for step in ("normalized", "redirects"):
            for item in q.get(step, []):
                for req, cur in list(alias.items()):
                    if cur == item["from"]:
                        alias[req] = item["to"]
        pages = {p["title"]: p for p in q.get("pages", [])}
        attach_tab_infoboxes(pages)
        for req, final in alias.items():
            page = pages.get(final)
            result[req] = page if page and not page.get("missing") and not page.get("invalid") else None
    return result


def page_text(page: dict) -> str:
    return page.get("revisions", [{}])[0].get("slots", {}).get("main", {}).get("content", "")


def attach_tab_infoboxes(pages: dict[str, dict]) -> None:
    """Major characters keep their infobox in a "{{Name Tabs Top}}" template.

    For those pages, fetch the template and store its text as page["infobox_text"].
    """
    wanted = {}
    for title, page in pages.items():
        text = page_text(page)
        if INFOBOX_RE.search(text):
            continue
        m = re.search(r"\{\{([^{}|\n]+ Tabs Top)\s*\}\}", text)
        if m:
            wanted[title] = "Template:" + m.group(1).strip()
    templates = list(dict.fromkeys(wanted.values()))
    for i in range(0, len(templates), BATCH):
        data = api_get({
            "action": "query",
            "prop": "revisions",
            "rvprop": "content",
            "rvslots": "main",
            "titles": "|".join(templates[i:i + BATCH]),
        })
        found = {p["title"]: page_text(p) for p in data.get("query", {}).get("pages", [])}
        for title, template in wanted.items():
            if template in found:
                pages[title]["infobox_text"] = found[template]


def search(name: str) -> list[str]:
    data = api_get({"action": "query", "list": "search", "srsearch": name, "srlimit": "5", "srnamespace": "0"})
    return [hit["title"] for hit in data.get("query", {}).get("search", [])]


# ----------------------------------------------------------------- wikitext

def tokens(text: str) -> set[str]:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def strip_templates(text: str, names: tuple[str, ...]) -> str:
    """Remove {{Name ...}} templates (with nesting) for the given template names."""
    out, i = [], 0
    lowered = text.lower()
    while i < len(text):
        hit = None
        if text.startswith("{{", i):
            for n in names:
                if lowered.startswith("{{" + n.lower(), i):
                    hit = n
                    break
        if hit:
            depth, j = 0, i
            while j < len(text):
                if text.startswith("{{", j):
                    depth += 1
                    j += 2
                elif text.startswith("}}", j):
                    depth -= 1
                    j += 2
                    if depth == 0:
                        break
                else:
                    j += 1
            i = j
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def clean(value: str) -> str:
    v = strip_templates(value, ("Qref", "Ref", "Cite", "Fact", "Citation"))
    v = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", v, flags=re.S)
    v = re.sub(r"<br\s*/?>", "; ", v)
    v = re.sub(r"<[^>]+>", "", v)
    # {{Nihongo|"Mr. 1"|...}} -> "Mr. 1"
    for _ in range(3):
        v = re.sub(r"\{\{Nihongo\|([^|{}]*)(?:\|[^{}]*)?\}\}", r"\1", v)
        v = re.sub(r"\{\{Ruby\|([^|{}]*)\|[^{}]*\}\}", r"\1", v)
        v = re.sub(r"\{\{W\|[^|{}]*\|([^{}]*)\}\}", r"\1", v)
        v = re.sub(r"\{\{W\|([^|{}]*)\}\}", r"\1", v)
        v = re.sub(r"\{\{B\}\}", "", v)
        v = re.sub(r"\{\{[^{}]*\}\}", "", v)
    v = re.sub(r"\[\[(?:File|Image):[^\]]*\]\]", "", v)
    v = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", v)
    v = re.sub(r"\[\[([^\]]*)\]\]", r"\1", v)
    v = re.sub(r"\[https?://\S+ ([^\]]*)\]", r"\1", v)
    v = v.replace("'''", "").replace("''", "")
    v = re.sub(r"\s+", " ", v)
    v = re.sub(r"(?:\s*;\s*)+", "; ", v)
    v = re.sub(r"\(\s*;\s*", "(", v)
    v = v.strip(" ;,")
    return v


def infobox(wikitext: str) -> dict:
    m = INFOBOX_RE.search(wikitext)
    if not m:
        return {}
    start = m.start()
    depth, j = 0, start
    while j < len(wikitext):
        if wikitext.startswith("{{", j):
            depth += 1
            j += 2
        elif wikitext.startswith("}}", j):
            depth -= 1
            j += 2
            if depth == 0:
                break
        else:
            j += 1
    body = wikitext[start + 2:j - 2]
    # Split on top-level "|" that start a "key = value" line.
    fields, key, buf = {}, None, []
    for line in body.split("\n"):
        m = re.match(r"^\s*\|\s*([a-z0-9 ]+?)\s*=(.*)$", line, re.I)
        if m:
            if key:
                fields[key] = "\n".join(buf)
            key, buf = m.group(1).strip().lower(), [m.group(2)]
        elif key:
            buf.append(line)
    if key:
        fields[key] = "\n".join(buf)

    out = {}
    for src, dst in FIELDS.items():
        raw = fields.get(src)
        if not raw:
            continue
        value = clean(raw)
        if not value:
            continue
        if dst in LIST_FIELDS:
            out[dst] = [p.strip() for p in re.split(r";\s*", value) if p.strip()]
        else:
            out[dst] = value
    if "bounty" in out:
        out["bounty"] = out["bounty"].split(";")[0].strip()
    return out


def is_character_page(page: dict) -> bool:
    text = page_text(page)
    if re.search(r"\{\{\s*Disambig", text, re.I):
        return False
    return bool(INFOBOX_RE.search(page.get("infobox_text") or text))


def page_record(page: dict) -> dict:
    text = page.get("infobox_text") or page_text(page)
    rec = {
        "title": page["title"],
        "url": page.get("canonicalurl") or WIKI + urllib.parse.quote(page["title"].replace(" ", "_")),
        "image": None,
        "thumbnail": None,
        "info": infobox(text),
    }
    if page.get("original"):
        o = page["original"]
        rec["image"] = {"url": o["source"], "width": o.get("width"), "height": o.get("height")}
    if page.get("thumbnail"):
        t = page["thumbnail"]
        rec["thumbnail"] = {"url": t["source"], "width": t.get("width"), "height": t.get("height")}
    return rec


# --------------------------------------------------------------------- main

def candidates(entry: dict) -> list[str]:
    out = [entry["name"]]
    if entry.get("alias"):
        out += [f"{entry['name']} ({entry['alias']})", entry["alias"]]
    # The source uses curly apostrophes; wiki titles use straight ones.
    out += [t.replace("’", "'") for t in out]
    return list(dict.fromkeys(out))


def plausible(name: str, alias: str | None, title: str) -> bool:
    """Accept a search hit only if its title clearly names this character."""
    t = tokens(re.sub(r"\(.*?\)", "", title))
    for want in filter(None, (name, alias)):
        w = tokens(want)
        if w and (w <= t or (t and t <= w and len(t) >= max(1, len(w) - 1))):
            return True
    return False


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))["days"]
    overrides = json.loads(OVERRIDES.read_text(encoding="utf-8")) if OVERRIDES.exists() else {}
    overrides = {k: v for k, v in overrides.items() if not k.startswith("_")}

    entries = {}
    for day_entries in source.values():
        for e in day_entries:
            entries.setdefault(e["name"], e)

    resolved: dict[str, dict | None] = {}

    # 1. overrides
    forced = {n: t for n, t in overrides.items() if n in entries}
    for name, title in forced.items():
        resolved[name] = None
    titles = [t for t in forced.values() if t]
    pages = fetch_pages(titles) if titles else {}
    for name, title in forced.items():
        if title and pages.get(title) and is_character_page(pages[title]):
            resolved[name] = page_record(pages[title])
        elif title:
            print(f"  override for {name!r} -> {title!r} did not resolve to a character page")

    # 2. exact titles
    todo = [n for n in entries if n not in resolved]
    cand_map = {n: candidates(entries[n]) for n in todo}
    all_titles = list(dict.fromkeys(t for c in cand_map.values() for t in c))
    print(f"Looking up {len(all_titles)} titles for {len(todo)} characters...")
    pages = fetch_pages(all_titles)
    for name in todo:
        for title in cand_map[name]:
            page = pages.get(title)
            if page and is_character_page(page):
                resolved[name] = page_record(page)
                break

    # 3. search fallback
    misses = [n for n in entries if n not in resolved]
    print(f"Searching for {len(misses)} unmatched characters...")
    hits = {}
    for name in misses:
        for title in search(name):
            if plausible(name, entries[name].get("alias"), title):
                hits[name] = title
                break
    pages = fetch_pages(list(dict.fromkeys(hits.values()))) if hits else {}
    for name, title in hits.items():
        page = pages.get(title)
        if page and is_character_page(page):
            resolved[name] = page_record(page)
            resolved[name]["matched_by"] = "search"

    for name in entries:
        resolved.setdefault(name, None)

    OUT.write_text(json.dumps(dict(sorted(resolved.items(), key=lambda kv: kv[0].lower())),
                              ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    found = sum(1 for v in resolved.values() if v)
    images = sum(1 for v in resolved.values() if v and v["image"])
    print(f"Matched {found}/{len(entries)} characters ({images} with images) -> {OUT}")
    unmatched = sorted(n for n, v in resolved.items() if not v)
    if unmatched:
        print("Unmatched:", ", ".join(unmatched))


if __name__ == "__main__":
    main()
