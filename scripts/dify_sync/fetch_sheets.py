#!/usr/bin/env python3
"""Fetch Google Sheets data and save as JSON."""

import json
import os
import sys

from google.oauth2 import service_account
from googleapiclient.discovery import build

from config import GOOGLE_SERVICE_ACCOUNT_KEY, GOOGLE_SHEETS, SHEETS_DIR


SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def get_sheets_service():
    """Build Google Sheets API service from service account key."""
    key_json = GOOGLE_SERVICE_ACCOUNT_KEY
    if not key_json:
        print("Error: GOOGLE_SERVICE_ACCOUNT_KEY not set", file=sys.stderr)
        sys.exit(1)

    # The key may be a JSON string (from env/secret) or a file path
    if os.path.isfile(key_json):
        creds = service_account.Credentials.from_service_account_file(key_json, scopes=SCOPES)
    else:
        info = json.loads(key_json)
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)

    return build("sheets", "v4", credentials=creds)


def fetch_sheet(service, sheet_id, sheet_name):
    """Fetch all data from a Google Sheet. Returns list of row dicts."""
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range="A:ZZ"
        ).execute()
    except Exception as e:
        print(f"  Error fetching '{sheet_name}': {e}", file=sys.stderr)
        return None

    rows = result.get("values", [])
    if not rows:
        return []

    # First row is header
    headers = rows[0]
    data = []
    for row in rows[1:]:
        padded = row + [""] * (len(headers) - len(row))
        data.append(dict(zip(headers, padded)))

    return data


def main():
    os.makedirs(SHEETS_DIR, exist_ok=True)
    service = get_sheets_service()

    total = 0
    errors = 0
    for sheet_cfg in GOOGLE_SHEETS:
        sheet_id = sheet_cfg["id"]
        slug = sheet_cfg["slug"]
        name = sheet_cfg["name"]

        if not sheet_id:
            print(f"  Skipping '{name}': no sheet ID configured", file=sys.stderr)
            continue

        print(f"  Fetching: {name} ({slug})...", file=sys.stderr)
        data = fetch_sheet(service, sheet_id, name)

        if data is None:
            errors += 1
            continue

        out_path = os.path.join(SHEETS_DIR, f"{slug}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"name": name, "slug": slug, "rows": data}, f, ensure_ascii=False, indent=2)

        total += 1
        print(f"  Saved: {slug}.json ({len(data)} rows)", file=sys.stderr)

    print(f"Fetched {total} sheets ({errors} errors)", file=sys.stderr)
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
