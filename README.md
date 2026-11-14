# One Piece Birthday API

A static JSON API of One Piece character birthdays, built to be hosted on GitHub Pages (or any static host). There is no server: every endpoint is a pre-built `.json` file.

## Endpoints

| Path | Returns |
| --- | --- |
| `v1/dates/MM-DD.json` | `{ date, label, month, day, characters: [...] }` for one day. All 366 days exist, including `02-29`. |
| `v1/months/MM.json` | `{ month, name, count, days: [...] }` |
| `v1/all.json` | `{ count, days: [...] }` for the whole year |
| `v1/characters.json` | `{ count, characters: [{ name, slug, dates }] }` |
| `v1/index.json` | Counts and the endpoint list |

`index.html` is a small docs page that shows today's birthdays and has a search box.

There is no `today` endpoint, because a static host can't work out the date. Clients compute `MM-DD` in their own timezone and fetch that file:

```js
const d = new Date();
const key = `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const { characters } = await fetch(`https://<user>.github.io/<repo>/v1/dates/${key}.json`).then(r => r.json());
```

GitHub Pages sends `Access-Control-Allow-Origin: *`, so browsers on other sites can fetch these files.

## Updating the data

Edit `data/birthdays.json` (keys are labels like `"October 22nd"`), then rebuild:

```bash
python build.py
```

The build uses only the Python standard library. It wipes and rewrites `v1/`, rejects bad or duplicate date labels, and drops blank names. Commit the regenerated `v1/` along with the data change.

## Hosting on GitHub Pages

Pages serves a branch from either its root or `/docs`, so this folder works best as its own repository:

1. Copy this folder into a new public repo (Pages on private repos needs a paid plan).
2. Repo **Settings → Pages → Build and deployment**: Source *Deploy from a branch*, branch `main`, folder `/ (root)`.
3. The API is then live at `https://<user>.github.io/<repo>/v1/...`.

`.nojekyll` stops Pages from running Jekyll over the files.
