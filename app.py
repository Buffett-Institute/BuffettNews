import os

from flask import Flask, jsonify, request, send_file

import spreadsheet
from extractor import ExtractionError, extract_article_metadata

app = Flask(__name__, static_folder="static", template_folder="templates")

XLSX_PATH = os.environ.get(
    "XLSX_PATH", os.path.join(os.path.dirname(__file__), "data", "Test Buffett_News.xlsx")
)

@app.route("/")
def index():
    with open(os.path.join(app.template_folder, "index.html"), encoding="utf-8") as f:
        return f.read()


@app.route("/api/preview", methods=["POST"])
def preview():
    payload = request.get_json(force=True) or {}
    url = (payload.get("url") or "").strip()
    note = (payload.get("note") or "").strip()
    if not url:
        return jsonify({"error": "Please provide an article URL."}), 400
    if not note:
        return jsonify({"error": "Please provide a sentence about the Buffett Institute connection."}), 400
    try:
        meta = extract_article_metadata(url, note)
    except ExtractionError as exc:
        return jsonify({"error": str(exc), "blocked": True}), 502
    except Exception as exc:  # noqa: BLE001 - surface any scraping failure to the UI
        return jsonify({"error": f"Unexpected error while scraping the article: {exc}"}), 500
    return jsonify(meta)


@app.route("/api/save", methods=["POST"])
def save():
    payload = request.get_json(force=True) or {}
    required = ["title", "url"]
    missing = [f for f in required if not (payload.get(f) or "").strip()]
    if missing:
        return jsonify({"error": f"Missing required field(s): {', '.join(missing)}"}), 400
    try:
        row = spreadsheet.append_row(XLSX_PATH, payload)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"Could not write to the spreadsheet: {exc}"}), 500
    return jsonify({"ok": True, "row": row})


@app.route("/api/recent")
def recent():
    try:
        rows = spreadsheet.read_recent_rows(XLSX_PATH, limit=10)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500
    return jsonify({"rows": rows})


@app.route("/download")
def download():
    return send_file(XLSX_PATH, as_attachment=True, download_name="Buffett_News_Page.xlsx")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="127.0.0.1", port=port, debug=True)
