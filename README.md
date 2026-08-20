# BuffettNews

A small local web app that automates filling out the Buffett News Page
spreadsheet. Paste an article URL and a note about how it connects to the
Roberta Buffett Institute, review the auto-filled fields, and it appends a
new row to `data/Buffett_News_Page.xlsx`.

## What it fills in automatically

From the article URL, the app scrapes Open Graph tags, meta tags, and
JSON-LD structured data to guess:

- **Title** — converted to title case
- **Publication date**
- **Source** (outlet or journal name)
- **Image alt text** — pulled from the article's main image; if there's no
  image on the page, falls back to the author's name
- **Short description** — the article's own meta description, stitched
  together with the connection note you typed in

Every field is shown in an editable preview before anything is written to
the spreadsheet, so a wrong guess just needs a quick correction rather than
a redo. `Approved`, `Posted`, and `Image Title in Canva` stay manual, since
those depend on human review and your Canva workflow, not on the article
itself.

## Running it locally

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5000 in your browser.

By default it reads/writes `data/Buffett_News_Page.xlsx`. That file isn't
checked into git (it's data, not code, and would churn the history with
binary diffs every time a row is added) — copy your working spreadsheet to
`data/Buffett_News_Page.xlsx` before the first run. To point it at a
different file entirely (e.g. one synced via Dropbox/OneDrive), set the
`XLSX_PATH` environment variable before running:

```bash
XLSX_PATH=/path/to/Buffett_News_Page.xlsx python app.py
```

Use the **Download current spreadsheet** link in the app to grab the
updated file at any time.

## Why this runs locally instead of on GitHub Pages

GitHub Pages only serves static files — it can't run the Python server that
fetches article pages and writes to the spreadsheet. Fetching arbitrary
article URLs directly from JavaScript in a browser is also blocked by most
sites' CORS policies, so a purely static page can't scrape articles either.
This needs a small backend, which is why it's built as a local Flask app.

If you'd like this reachable from a browser without anyone running it
locally, the same Flask app can be deployed as-is to a free/low-cost host
like Render, Railway, or PythonAnywhere — ask if you'd like help setting
that up.

## Project layout

- `app.py` — Flask routes (preview, save, recent rows, download)
- `extractor.py` — article scraping and metadata heuristics
- `spreadsheet.py` — appends a row to the xlsx, matching existing formatting
- `templates/index.html` — the two-step intake form
- `data/Buffett_News_Page.xlsx` — the spreadsheet the app reads and writes
