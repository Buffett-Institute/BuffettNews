"""
Appends a new row to the Buffett News Page spreadsheet, matching the
existing sheet's columns and per-cell formatting exactly.
"""
from copy import copy
from datetime import datetime

import openpyxl

COLUMNS = [
    "approved", "posted", "title", "date", "url", "source",
    "canva_title", "image_alt", "short_description", "content_type",
]
HEADER_ROW = 2
STYLE_SOURCE_ROW = 3


def _next_empty_row(ws) -> int:
    row = HEADER_ROW + 1
    while ws.cell(row=row, column=3).value not in (None, ""):
        row += 1
    return row


def append_row(xlsx_path: str, data: dict) -> int:
    """data keys: approved, posted, title, date (YYYY-MM-DD str or empty),
    url, source, canva_title, image_alt, short_description, content_type.
    Returns the row number written."""
    wb = openpyxl.load_workbook(xlsx_path)
    ws = wb["Sheet1"]
    row = _next_empty_row(ws)

    values = {
        1: data.get("approved", "") or "",
        2: data.get("posted", "") or "",
        3: data.get("title", "") or "",
        4: data.get("date") or "",
        5: data.get("url", "") or "",
        6: data.get("source", "") or "",
        7: data.get("canva_title", "") or "",
        8: data.get("image_alt", "") or "",
        9: data.get("short_description", "") or "",
        10: data.get("content_type", "") or "",
    }
    if values[4]:
        try:
            values[4] = datetime.strptime(values[4], "%Y-%m-%d")
        except ValueError:
            pass  # leave as free text if it doesn't parse

    for col in range(1, 11):
        src_cell = ws.cell(row=STYLE_SOURCE_ROW, column=col)
        dst_cell = ws.cell(row=row, column=col)
        dst_cell.value = values[col]
        dst_cell.font = copy(src_cell.font)
        dst_cell.alignment = copy(src_cell.alignment)
        dst_cell.fill = copy(src_cell.fill)
        dst_cell.border = copy(src_cell.border)
        dst_cell.number_format = src_cell.number_format

    wb.save(xlsx_path)
    return row


def read_recent_rows(xlsx_path: str, limit: int = 10):
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb["Sheet1"]
    last = HEADER_ROW
    for r in range(HEADER_ROW + 1, ws.max_row + 1):
        if ws.cell(row=r, column=3).value:
            last = r
    start = max(HEADER_ROW + 1, last - limit + 1)
    rows = []
    for r in range(start, last + 1):
        if not ws.cell(row=r, column=3).value:
            continue
        date_val = ws.cell(row=r, column=4).value
        rows.append({
            "row": r,
            "approved": ws.cell(row=r, column=1).value,
            "posted": ws.cell(row=r, column=2).value,
            "title": ws.cell(row=r, column=3).value,
            "date": date_val.strftime("%Y-%m-%d") if hasattr(date_val, "strftime") else (date_val or ""),
            "url": ws.cell(row=r, column=5).value,
            "source": ws.cell(row=r, column=6).value,
            "content_type": ws.cell(row=r, column=10).value,
        })
    rows.reverse()
    return rows
