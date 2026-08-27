"""
Appends a new row to the Buffett News Page Google Sheet, replacing the old
local .xlsx storage. Authenticates as a service account.

Service accounts can't create their own spreadsheets (personal accounts
have no Drive storage quota), so GOOGLE_SHEET_ID must point at a sheet you
created yourself and shared with the service account's email as Editor.
The headers/formatting are applied automatically the first time the app
touches a blank sheet. The resolved ID is cached in SHEET_ID_PATH so it
isn't re-resolved on every request.
"""
import json
import os
import re

from datetime import datetime, timedelta

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

HEADER_LABELS = [
    "approved", "posted", "title", "date", "url", "source",
    "canva_title", "image_alt", "short_description", "content_type",
]
COLUMN_WIDTHS = [90, 80, 320, 100, 260, 180, 200, 320, 480, 150]
SHEET_TITLE = "Sheet1"
DOC_TITLE = os.environ.get("GOOGLE_SHEET_TITLE", "Buffett News Page")
HEADER_ROW = 2  # 1-indexed; row 1 is the merged title banner
DATA_START_ROW = HEADER_ROW + 1  # newest row always lands here

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

SERVICE_ACCOUNT_FILE = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")
SHEET_ID_PATH = os.environ.get("SHEET_ID_PATH", os.path.join("data", "sheet_id.json"))

def _extract_sheet_id(value):
    """Accepts either a bare sheet ID or a full Google Sheets URL and
    returns just the ID."""
    if not value:
        return value
    match = re.search(r"/d/([a-zA-Z0-9-_]+)", value)
    return match.group(1) if match else value


# Fallback if the GOOGLE_SHEET_ID environment variable isn't set/visible to
# the process — paste the sheet's ID (or its full URL) here. The env var
# still wins when both are set.
HARDCODED_SHEET_ID = ""
GOOGLE_SHEET_ID = _extract_sheet_id(os.environ.get("GOOGLE_SHEET_ID") or HARDCODED_SHEET_ID)


class SheetError(Exception):
    pass


_sheets_service = None


def _get_credentials():
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        raise SheetError(
            f"Google service account key not found at '{SERVICE_ACCOUNT_FILE}'. "
            "Set GOOGLE_SERVICE_ACCOUNT_FILE or drop the key at that path."
        )
    return service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )


def _sheets():
    global _sheets_service
    if _sheets_service is None:
        _sheets_service = build("sheets", "v4", credentials=_get_credentials(), cache_discovery=False)
    return _sheets_service


def _load_cached_sheet():
    if not os.path.exists(SHEET_ID_PATH):
        return None
    with open(SHEET_ID_PATH, encoding="utf-8") as f:
        return json.load(f)


def _cache_sheet(spreadsheet_id, sheet_id, url):
    os.makedirs(os.path.dirname(SHEET_ID_PATH) or ".", exist_ok=True)
    with open(SHEET_ID_PATH, "w", encoding="utf-8") as f:
        json.dump({"spreadsheet_id": spreadsheet_id, "sheet_id": sheet_id, "url": url}, f)


def _title_format():
    return {
        "backgroundColor": {"red": 0x85 / 255, "green": 0xB1 / 255, "blue": 0xF2 / 255},
        "textFormat": {"bold": True, "fontSize": 16},
        "horizontalAlignment": "LEFT",
    }


def _header_format():
    return {
        "backgroundColor": {"red": 0x8A / 255, "green": 0xAC / 255, "blue": 0xDE / 255},
        "textFormat": {"bold": True, "fontSize": 11},
        "horizontalAlignment": "CENTER",
        "verticalAlignment": "MIDDLE",
    }


def _body_format():
    return {
        "wrapStrategy": "WRAP",
        "horizontalAlignment": "LEFT",
        "borders": {
            side: {"style": "SOLID", "width": 1, "color": {"red": 0, "green": 0, "blue": 0}}
            for side in ("top", "bottom", "left", "right")
        },
    }


def _formatting_requests(sheet_id):
    requests = [
        {"updateSheetProperties": {
            "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": HEADER_ROW}},
            "fields": "gridProperties.frozenRowCount",
        }},
        {"mergeCells": {
            "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1,
                      "startColumnIndex": 0, "endColumnIndex": len(HEADER_LABELS)},
            "mergeType": "MERGE_ALL",
        }},
        {"updateCells": {
            "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1,
                      "startColumnIndex": 0, "endColumnIndex": 1},
            "rows": [{"values": [{
                "userEnteredValue": {"stringValue": DOC_TITLE},
                "userEnteredFormat": _title_format(),
            }]}],
            "fields": "userEnteredValue,userEnteredFormat",
        }},
        {"updateCells": {
            "range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 2,
                      "startColumnIndex": 0, "endColumnIndex": len(HEADER_LABELS)},
            "rows": [{"values": [
                {"userEnteredValue": {"stringValue": label}, "userEnteredFormat": _header_format()}
                for label in HEADER_LABELS
            ]}],
            "fields": "userEnteredValue,userEnteredFormat",
        }},
    ]
    for i, width in enumerate(COLUMN_WIDTHS):
        requests.append({"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": i, "endIndex": i + 1},
            "properties": {"pixelSize": width},
            "fields": "pixelSize",
        }})
    return requests


def _is_blank(spreadsheet_id):
    sheets = _sheets()
    resp = sheets.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=f"{SHEET_TITLE}!A1:A2"
    ).execute()
    return not resp.get("values")


def _adopt_existing_sheet(env_id):
    sheets = _sheets()
    meta = sheets.spreadsheets().get(
        spreadsheetId=env_id, fields="spreadsheetId,spreadsheetUrl,sheets.properties"
    ).execute()
    sheet_props = next(
        (s["properties"] for s in meta["sheets"] if s["properties"]["title"] == SHEET_TITLE),
        meta["sheets"][0]["properties"],
    )
    resolved = {
        "spreadsheet_id": meta["spreadsheetId"],
        "sheet_id": sheet_props["sheetId"],
        "url": meta.get("spreadsheetUrl") or f"https://docs.google.com/spreadsheets/d/{env_id}",
    }

    if _is_blank(resolved["spreadsheet_id"]):
        sheets.spreadsheets().batchUpdate(
            spreadsheetId=resolved["spreadsheet_id"],
            body={"requests": _formatting_requests(resolved["sheet_id"])},
        ).execute()

    _cache_sheet(**resolved)
    return resolved


def _resolve_sheet():
    """Returns {"spreadsheet_id", "sheet_id", "url"}."""
    if not GOOGLE_SHEET_ID:
        raise SheetError(
            "No Google Sheet ID configured. Create a Google Sheet, share it with the "
            "service account's email as Editor, and either set the GOOGLE_SHEET_ID "
            "environment variable or fill in HARDCODED_SHEET_ID in spreadsheet.py "
            "(see README.md)."
        )
    cached = _load_cached_sheet()
    if cached and cached.get("spreadsheet_id") == GOOGLE_SHEET_ID:
        return cached
    return _adopt_existing_sheet(GOOGLE_SHEET_ID)


def sheet_url() -> str:
    return _resolve_sheet()["url"]


def append_row(_unused_path, data: dict) -> int:
    """data keys: approved, posted, title, date (YYYY-MM-DD str or empty),
    url, source, canva_title, image_alt, short_description, content_type.
    Inserts as the newest row, directly under the header. Returns the row
    number written (always DATA_START_ROW, since new rows always land there)."""
    sheet = _resolve_sheet()
    sheets = _sheets()

    values = [
        data.get("approved", "") or "",
        data.get("posted", "") or "",
        data.get("title", "") or "",
        data.get("date", "") or "",
        data.get("url", "") or "",
        data.get("source", "") or "",
        data.get("canva_title", "") or "",
        data.get("image_alt", "") or "",
        data.get("short_description", "") or "",
        data.get("content_type", "") or "",
    ]

    row_cells = []
    for i, val in enumerate(values):
        if i == 3 and val:
            try:
                dt = datetime.strptime(val, "%Y-%m-%d")
                serial = (dt - datetime(1899, 12, 30)).days
                cell = {
                    "userEnteredValue": {"numberValue": serial},
                    "userEnteredFormat": {**_body_format(), "numberFormat": {"type": "DATE", "pattern": "mm/dd/yy"}},
                }
                row_cells.append(cell)
                continue
            except ValueError:
                pass
        row_cells.append({"userEnteredValue": {"stringValue": val}, "userEnteredFormat": _body_format()})

    start_index = DATA_START_ROW - 1  # 0-based
    requests = [
        {"insertDimension": {
            "range": {"sheetId": sheet["sheet_id"], "dimension": "ROWS",
                      "startIndex": start_index, "endIndex": start_index + 1},
            "inheritFromBefore": False,
        }},
        {"updateCells": {
            "range": {"sheetId": sheet["sheet_id"], "startRowIndex": start_index, "endRowIndex": start_index + 1,
                      "startColumnIndex": 0, "endColumnIndex": len(values)},
            "rows": [{"values": row_cells}],
            "fields": "userEnteredValue,userEnteredFormat",
        }},
    ]
    try:
        sheets.spreadsheets().batchUpdate(spreadsheetId=sheet["spreadsheet_id"], body={"requests": requests}).execute()
    except HttpError as exc:
        raise SheetError(f"Could not write to the Google Sheet: {exc}") from exc
    return DATA_START_ROW


def read_recent_rows(_unused_path, limit: int = 10):
    sheet = _resolve_sheet()
    sheets = _sheets()
    last_row = DATA_START_ROW + limit - 1
    range_ = f"{SHEET_TITLE}!A{DATA_START_ROW}:J{last_row}"
    try:
        resp = sheets.spreadsheets().values().get(
            spreadsheetId=sheet["spreadsheet_id"], range=range_,
            valueRenderOption="UNFORMATTED_VALUE", dateTimeRenderOption="SERIAL_NUMBER",
        ).execute()
    except HttpError as exc:
        raise SheetError(f"Could not read the Google Sheet: {exc}") from exc

    rows = []
    for offset, row in enumerate(resp.get("values", [])):
        row = row + [""] * (10 - len(row))
        if not row[2]:
            break
        date_val = row[3]
        if isinstance(date_val, (int, float)):
            date_val = (datetime(1899, 12, 30) + timedelta(days=date_val)).strftime("%Y-%m-%d")
        rows.append({
            "row": DATA_START_ROW + offset,
            "approved": row[0],
            "posted": row[1],
            "title": row[2],
            "date": date_val,
            "url": row[4],
            "source": row[5],
            "content_type": row[9],
        })
    return rows
