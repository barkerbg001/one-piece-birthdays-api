# One Piece Birthday API

A static JSON API of One Piece character birthdays, with character images and info. It's hosted on GitHub Pages: every endpoint is a pre-built `.json` file, so there's no server, key or rate limit.

**Live:** https://barkerbg001.github.io/one-piece-birthdays-api/

## Endpoints

| Path | Returns |
| --- | --- |
| `v1/dates/MM-DD.json` | One day: `names` (display strings) and `characters` (compact objects). All 366 days exist, including `02-29`. |
| `v1/months/MM.json` | Every day in a month, plus `calendar_image` (the Library of Ohara's illustrated calendar for that month). |
| `v1/characters/{id}.json` | One character in full (see below). |
| `v1/characters.json` | Every character in compact form, with their birthday dates. |
| `v1/all.json` | The whole calendar. |
| `v1/index.json` | Counts, endpoint list and sources. |

### Character fields

```jsonc
{
  "id": "daz-bones",
  "name": "Daz Bones",
  "display_name": "Daz Bones (Mr. 1)",
  "alias": "Mr. 1",
  "note": null,                       // editor's note from the source, e.g. a retcon
  "birthdays": [{ "date": "01-01", "label": "January 1st" }],
  "born_with": [],                    // twins/siblings sharing the birthday: [{ id, name }]
  "image":     { "url": "...", "width": 400, "height": 800 },
  "thumbnail": { "url": "...", "width": 200, "height": 400 },
  "wiki": { "title": "Daz Bonez", "url": "https://onepiece.fandom.com/wiki/Daz_Bonez" },
  "info": {
    "japanese_name": "ダズ・ボーネス", "romanized_name": "Dazu Bōnesu",
    "epithet": "The Killer", "affiliations": ["Cross Guild", "Baroque Works (former)"],
    "occupations": [...], "origin": "West Blue", "debut": ["Chapter 160", "Episode 103"],
    "bounty": "75,000,000", "devil_fruit": "Supa Supa no Mi", "devil_fruit_english": "Dice-Dice Fruit",
    "devil_fruit_type": "Paramecia", "age": "...", "height": "...", "blood_type": "F", "birthday": "January 1st"
  }
}
```

`info` only contains the fields the wiki has for that character. `image`, `thumbnail` and `wiki` are `null` for the few characters without a wiki page. In the date and month listings, each character is a compact summary with `thumbnail`, `image`, `wiki_url`, `epithet`, the first `affiliation`, and an `api` path to the full record.

### Today's birthdays

There's no `today` endpoint, because a static host can't work out the date. Work out `MM-DD` in your own timezone and fetch that file:

```js
const d = new Date();
const key = `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const day = await fetch(`https://barkerbg001.github.io/one-piece-birthdays-api/v1/dates/${key}.json`).then(r => r.json());
```

GitHub Pages sends `Access-Control-Allow-Origin: *`, so browser code on any site can fetch the JSON.

### Images

Images aren't copied into this repo. They're links to the One Piece Wiki's CDN (`static.wikia.nocookie.net`), which turns away requests that have no `Referer` header. Browsers send one for `<img>` tags, so embedding works. For server-side downloads, send a `Referer` header with your site's URL.

## Data sources

- **Birthdays:** [The Library of Ohara – Birthday Calendar](https://thelibraryofohara.com/birthday-calendar/). Its square brackets (siblings and twins) become `born_with`, and parentheses become `alias` or `note`.
- **Character info and images:** [One Piece Wiki](https://onepiece.fandom.com/) infoboxes. The text is CC BY-SA 3.0. Images are © Eiichiro Oda / Shueisha / Toei Animation.

Where the two sources disagree on a birthday, this API follows the Library of Ohara. The wiki's value stays in `info.birthday`.

## Updating

```bash
python scripts/fetch_source.py   # re-scrape the Library of Ohara -> data/source.json
python scripts/fetch_wiki.py     # match characters on the wiki   -> data/wiki.json (cached in .cache/)
python build.py                  # regenerate v1/
```

All three scripts use only the Python standard library. `fetch_wiki.py --refresh` ignores the cache. If a character gets matched to the wrong wiki page, or to none, add an entry to `data/wiki_overrides.json` (use `null` for "no match") and rerun. Commit the regenerated `v1/` and Pages redeploys on its own.
