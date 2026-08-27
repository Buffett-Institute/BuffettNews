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
flow — do this once before the first run:

1. In the [Google Cloud Console](https://console.cloud.google.com/), create
   (or reuse) a project, then enable the **Google Sheets API** and
   **Google Drive API** for it.
2. Under **IAM & Admin → Service Accounts**, create a service account and
   add a JSON key. Download it and save it as `service_account.json` in the
   project root (this file is gitignored — never commit it).
3. Set which of your own Google accounts should get edit access to the
   sheet the app creates, since a sheet made by the service account is
   otherwise only visible to that service account:

   ```bash
   export GOOGLE_SHEET_SHARE_WITH=you@example.com
   ```

4. Run the app. On the first save/preview it automatically creates a new
   Google Sheet titled "Buffett News Page" (headers, column widths, and
   formatting included), shares it with the address above, and caches its
   ID in `data/sheet_id.json` so later runs reuse the same sheet.

Environment variables, all optional:

| Variable | Default | Purpose |
| --- | --- | --- |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | `service_account.json` | Path to the service account key |
| `GOOGLE_SHEET_SHARE_WITH` | *(none)* | Comma-separated email(s) to share a newly created sheet with |
| `GOOGLE_SHEET_ID` | *(none)* | Point at an existing sheet instead of creating a new one |
| `GOOGLE_SHEET_TITLE` | `Buffett News Page` | Title used when creating a new sheet |
| `SHEET_ID_PATH` | `data/sheet_id.json` | Where the created sheet's ID is cached |

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
