# BuffettNews

A small local web app that automates filling out the Buffett News Page
spreadsheet. Paste an article URL and a note about how it connects to the
Roberta Buffett Institute, review the auto-filled fields, and it appends a
new row to a Google Sheet in the cloud.

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

### Google Sheets setup (one-time)

The app writes to a Google Sheet via a service account, so there's no login
flow. **Important:** service accounts can't create their own spreadsheets
(personal accounts have no Drive storage quota) — the app only reads and
writes a sheet you already own and have shared with it. Do this once
before the first run:

1. In the [Google Cloud Console](https://console.cloud.google.com/), create
   (or reuse) a project, then enable the **Google Sheets API** for it.
2. Under **IAM & Admin → Service Accounts**, create a service account and
   add a JSON key. Download it and save it as `service_account.json` in the
   project root (this file is gitignored — never commit it).
3. Go to [sheets.new](https://sheets.new) to create a blank Google Sheet
   under your own account. Click **Share**, paste in the service account's
   email (the `client_email` field in `service_account.json`, looks like
   `...@your-project.iam.gserviceaccount.com`), and give it **Editor**
   access.
4. Copy the sheet's ID out of its URL — the long string between `/d/` and
   `/edit` in `https://docs.google.com/spreadsheets/d/<SHEET_ID>/edit` —
   and set it before running the app:

   ```bash
   export GOOGLE_SHEET_ID=<SHEET_ID>
   ```

   If your environment doesn't reliably pass environment variables through
   to the app, you can instead paste the ID directly into
   `HARDCODED_SHEET_ID` near the top of `spreadsheet.py` — the env var
   still takes precedence if both are set.

5. Run the app. The first time it touches this sheet, it detects it's
   blank and fills in the title banner, headers, column widths, and
   formatting automatically, then caches the ID in `data/sheet_id.json` so
   it isn't re-resolved on every request.

Environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `GOOGLE_SHEET_ID` | *required* | The sheet you created and shared with the service account (see steps 3-4 above) |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | `service_account.json` | Path to the service account key |
| `GOOGLE_SHEET_TITLE` | `Buffett News Page` | Title written into the banner row when formatting a blank sheet |
| `SHEET_ID_PATH` | `data/sheet_id.json` | Where the resolved sheet's ID is cached |

Use the **Open Google Sheet** link in the app to jump to the live sheet at
any time.

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

- `app.py` — Flask routes (preview, save, recent rows, open sheet)
- `extractor.py` — article scraping and metadata heuristics
- `spreadsheet.py` — Google Sheets API client: creates/finds the sheet, appends rows, matches existing formatting
- `templates/index.html` — the two-step intake form
- `service_account.json` — your Google service account key (gitignored, not included)
- `data/sheet_id.json` — cached ID of the sheet the app created (gitignored, auto-generated)
