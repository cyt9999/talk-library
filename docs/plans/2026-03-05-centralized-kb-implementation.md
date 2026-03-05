# Centralized Knowledge Base — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a daily-automated pipeline that syncs all data sources (YouTube, tweets, Google Sheets, app guide) into an OpenAI Vector Store.

**Architecture:** Each data source has its own fetcher script outputting JSON to `data/`. A sync orchestrator converts all JSON to Markdown and uploads to the OpenAI Vector Store with smart diffing. A GitHub Action runs the pipeline daily.

**Tech Stack:** Python 3.12, OpenAI API (vector stores), Google Sheets API (`google-auth` + `google-api-python-client`), X API v2, GitHub Actions.

---

## Pre-requisites (Manual Steps)

Before starting implementation, these must be done by the user:

1. Add `X_BEARER_TOKEN` to GitHub repo secrets
2. Add `VECTOR_STORE_ID` to GitHub repo secrets
3. Share all 5 Google Sheets with the service account email (viewer/read-only)
4. Note the Google Sheet IDs (from each sheet's URL: `docs.google.com/spreadsheets/d/{SHEET_ID}/...`)

---

### Task 1: Update config.py with Google Sheets configuration

**Files:**
- Modify: `scripts/dify_sync/config.py`

**Step 1: Add Google Sheets config to config.py**

Add below the existing constants:

```python
# Google Sheets
SHEETS_DIR = os.path.join(ROOT_DIR, 'data', 'sheets')
DOCS_DIR = os.path.join(ROOT_DIR, 'data', 'docs')
GOOGLE_SERVICE_ACCOUNT_KEY = os.getenv("GOOGLE_SERVICE_ACCOUNT_KEY", "")

# Sheet ID → slug mapping. IDs come from the Google Sheet URL.
# User must fill in actual sheet IDs after sharing with service account.
GOOGLE_SHEETS = [
    {"id": os.getenv("SHEET_ID_MACRO", ""), "slug": "macro-announcements", "name": "投資talk君-總經公告"},
    {"id": os.getenv("SHEET_ID_POSITIONS", ""), "slug": "positions-ytd", "name": "投資Talk君-持倉績效 ytd"},
    {"id": os.getenv("SHEET_ID_DATASOURCES", ""), "slug": "data-sources", "name": "投資talk君-資料來源"},
    {"id": os.getenv("SHEET_ID_BETA", ""), "slug": "portfolio-beta", "name": "投資talk君-持倉Beta"},
    {"id": os.getenv("SHEET_ID_COMMUNITY", ""), "slug": "community-posts", "name": "爬蟲-投資talk君2025文章"},
]
```

**Step 2: Commit**

```bash
git add scripts/dify_sync/config.py
git commit -m "feat(config): add Google Sheets configuration"
```

---

### Task 2: Add google-auth dependencies

**Files:**
- Modify: `scripts/requirements.txt`

**Step 1: Add Google API dependencies**

Append to `scripts/requirements.txt`:

```
google-auth>=2.0.0
google-api-python-client>=2.0.0
```

**Step 2: Install locally to verify**

Run: `pip3 install google-auth google-api-python-client`

Expected: Installs without errors.

**Step 3: Commit**

```bash
git add scripts/requirements.txt
git commit -m "feat(deps): add google-auth and google-api-python-client"
```

---

### Task 3: Create fetch_sheets.py

**Files:**
- Create: `scripts/dify_sync/fetch_sheets.py`

**Step 1: Write the fetcher script**

```python
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
        import json as _json
        info = _json.loads(key_json)
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)

    return build("sheets", "v4", credentials=creds)


def fetch_sheet(service, sheet_id, sheet_name):
    """Fetch all data from a Google Sheet. Returns list of row dicts."""
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range="A:ZZ"  # Fetch all columns
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
        # Pad row to match header length
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
```

**Step 2: Test locally (requires a shared sheet + key)**

Run: `cd scripts/dify_sync && python3 fetch_sheets.py`

Expected: Creates `data/sheets/{slug}.json` files for each configured sheet. Sheets without IDs are skipped.

**Step 3: Commit**

```bash
git add scripts/dify_sync/fetch_sheets.py
git commit -m "feat: add Google Sheets fetcher script"
```

---

### Task 4: Create sync_vector_store.py — the orchestrator

**Files:**
- Create: `scripts/dify_sync/sync_vector_store.py`

**Step 1: Write the sync orchestrator**

```python
#!/usr/bin/env python3
"""Orchestrate: fetch all sources → convert to Markdown → diff → upload to vector store."""

import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime

from openai import OpenAI

from config import (
    VECTOR_STORE_ID, SUMMARIES_DIR, TWEETS_FILE,
    SHEETS_DIR, DOCS_DIR, ROOT_DIR
)
from convert_and_upload import (
    summary_to_markdown, tweets_to_markdown_by_week,
    get_or_create_vector_store
)

client = OpenAI()


def list_vector_store_files(vector_store_id):
    """List all files currently in the vector store. Returns {filename: file_id}."""
    existing = {}
    after = None
    while True:
        kwargs = {"vector_store_id": vector_store_id, "limit": 100}
        if after:
            kwargs["after"] = after
        page = client.vector_stores.files.list(**kwargs)
        for vs_file in page.data:
            # Get the original file to read its filename
            try:
                file_obj = client.files.retrieve(vs_file.id)
                existing[file_obj.filename] = vs_file.id
            except Exception:
                pass
        if not page.has_more:
            break
        after = page.data[-1].id
    return existing


def upload_file(vector_store_id, filename, content):
    """Upload a single Markdown file to the vector store."""
    tmp = tempfile.NamedTemporaryFile(
        mode='w', suffix='.md', delete=False, encoding='utf-8',
        prefix=filename.replace('.md', '_')
    )
    try:
        tmp.write(content)
        tmp.close()
        with open(tmp.name, 'rb') as f:
            file_obj = client.files.create(file=f, purpose="assistants")
        client.vector_stores.files.create_and_poll(
            vector_store_id=vector_store_id,
            file_id=file_obj.id
        )
    finally:
        os.unlink(tmp.name)


def delete_file(vector_store_id, file_id):
    """Remove a file from the vector store."""
    try:
        client.vector_stores.files.delete(vector_store_id=vector_store_id, file_id=file_id)
        client.files.delete(file_id)
    except Exception as e:
        print(f"  Warning: could not delete file {file_id}: {e}", file=sys.stderr)


def content_hash(text):
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:12]


def convert_summaries():
    """Convert YouTube summaries to Markdown. Returns list of (filename, content)."""
    results = []
    if not os.path.isdir(SUMMARIES_DIR):
        return results
    for fname in sorted(os.listdir(SUMMARIES_DIR)):
        if not fname.endswith('.json'):
            continue
        with open(os.path.join(SUMMARIES_DIR, fname), 'r', encoding='utf-8') as f:
            data = json.load(f)
        md = summary_to_markdown(data)
        md_filename = f"video-{fname.replace('.json', '.md')}"
        results.append((md_filename, md))
    return results


def convert_tweets():
    """Convert tweets to weekly Markdown files. Returns list of (filename, content)."""
    if not os.path.exists(TWEETS_FILE):
        return []
    with open(TWEETS_FILE, 'r', encoding='utf-8') as f:
        tweets = json.load(f)
    if not tweets:
        return []
    return tweets_to_markdown_by_week(tweets)


def convert_sheets():
    """Convert Google Sheets JSON to Markdown. Returns list of (filename, content)."""
    results = []
    if not os.path.isdir(SHEETS_DIR):
        return results
    today = datetime.now().strftime("%Y-%m-%d")
    for fname in sorted(os.listdir(SHEETS_DIR)):
        if not fname.endswith('.json'):
            continue
        with open(os.path.join(SHEETS_DIR, fname), 'r', encoding='utf-8') as f:
            data = json.load(f)

        name = data.get("name", fname)
        slug = data.get("slug", fname.replace(".json", ""))
        rows = data.get("rows", [])

        lines = [f"# {name}", f"- 資料更新日期：{today}", f"- 資料筆數：{len(rows)}", ""]

        if rows:
            headers = list(rows[0].keys())
            # Write as Markdown table
            lines.append("| " + " | ".join(headers) + " |")
            lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
            for row in rows:
                vals = [str(row.get(h, "")).replace("|", "\\|").replace("\n", " ") for h in headers]
                lines.append("| " + " | ".join(vals) + " |")

        md_filename = f"sheet-{slug}-latest.md"
        results.append((md_filename, "\n".join(lines)))

    return results


def convert_app_guide():
    """Read app guide Markdown if it exists. Returns list of (filename, content)."""
    guide_path = os.path.join(DOCS_DIR, "app-guide.md")
    if not os.path.exists(guide_path):
        return []
    with open(guide_path, 'r', encoding='utf-8') as f:
        content = f.read()
    if not content.strip():
        return []
    return [("app-guide.md", content)]


def sync(dry_run=False):
    """Main sync logic: convert all → diff → upload new/changed → delete removed."""
    vector_store = get_or_create_vector_store()
    vs_id = vector_store.id

    # 1. Convert all sources
    print("Converting sources to Markdown...", file=sys.stderr)
    all_files = []
    for label, converter in [
        ("YouTube summaries", convert_summaries),
        ("Tweets", convert_tweets),
        ("Google Sheets", convert_sheets),
        ("App guide", convert_app_guide),
    ]:
        files = converter()
        print(f"  {label}: {len(files)} files", file=sys.stderr)
        all_files.extend(files)

    local_map = {name: content for name, content in all_files}

    # 2. List existing files in vector store
    print("Listing vector store files...", file=sys.stderr)
    existing = list_vector_store_files(vs_id)
    print(f"  {len(existing)} files in vector store", file=sys.stderr)

    # 3. Determine what to upload / delete
    to_upload = []
    to_delete = []

    for name, content in all_files:
        if name not in existing:
            to_upload.append((name, content, "new"))
        elif name.startswith("sheet-") or name.startswith("tweets-"):
            # Always re-upload sheets (daily data) and current week tweets
            to_upload.append((name, content, "update"))
            to_delete.append((name, existing[name]))

    # Files in vector store but not locally → candidates for deletion
    for name, file_id in existing.items():
        if name not in local_map:
            to_delete.append((name, file_id))

    print(f"\nSync plan:", file=sys.stderr)
    print(f"  Upload: {len(to_upload)} files", file=sys.stderr)
    print(f"  Delete: {len(to_delete)} files", file=sys.stderr)

    if dry_run:
        for name, _, reason in to_upload:
            print(f"  [DRY RUN] Would upload: {name} ({reason})", file=sys.stderr)
        for name, _ in to_delete:
            print(f"  [DRY RUN] Would delete: {name}", file=sys.stderr)
        return

    # 4. Delete old versions first
    for name, file_id in to_delete:
        print(f"  Deleting: {name}", file=sys.stderr)
        delete_file(vs_id, file_id)

    # 5. Upload new/changed
    uploaded = 0
    for name, content, reason in to_upload:
        print(f"  Uploading: {name} ({reason})", file=sys.stderr)
        upload_file(vs_id, name, content)
        uploaded += 1

    print(f"\nSync complete: {uploaded} uploaded, {len(to_delete)} deleted", file=sys.stderr)


def main():
    dry_run = "--dry-run" in sys.argv
    sync(dry_run=dry_run)


if __name__ == "__main__":
    main()
```

**Step 2: Test with dry run**

Run: `cd scripts/dify_sync && python3 sync_vector_store.py --dry-run`

Expected: Lists what would be uploaded/deleted without actually doing anything.

**Step 3: Test actual sync**

Run: `cd scripts/dify_sync && python3 sync_vector_store.py`

Expected: Uploads new files, re-uploads sheets/tweets, deletes orphaned files.

**Step 4: Commit**

```bash
git add scripts/dify_sync/sync_vector_store.py
git commit -m "feat: add vector store sync orchestrator with smart diff"
```

---

### Task 5: Create app-guide.md placeholder

**Files:**
- Create: `data/docs/app-guide.md`

**Step 1: Write placeholder**

```markdown
# 投資Talk君 — 使用指南

> 本文件由作者手動維護。AI 問答機器人會根據此文件回答關於 App 使用方式的問題。

## 功能介紹

（待作者填寫：App 的主要功能說明）

## 常見問題

（待作者填寫：使用者常見問題與解答）

## 資料來源

- YouTube 影片摘要：每日自動更新
- X 平台短評：每日自動更新
- Google Sheets 數據：每日自動更新
- 社團貼文：歷史資料
```

**Step 2: Commit**

```bash
mkdir -p data/docs
git add data/docs/app-guide.md
git commit -m "docs: add app guide placeholder for vector store ingestion"
```

---

### Task 6: Create the GitHub Action workflow

**Files:**
- Create: `.github/workflows/daily-sync-kb.yml`

**Step 1: Write the workflow**

```yaml
name: Daily Sync Knowledge Base

on:
  # Run after daily-summarize completes
  workflow_run:
    workflows: ["Daily Summarize"]
    types: [completed]
  # Allow manual trigger
  workflow_dispatch:

permissions:
  contents: write

jobs:
  sync:
    runs-on: ubuntu-latest
    # Only run if the triggering workflow succeeded (or manual dispatch)
    if: ${{ github.event_name == 'workflow_dispatch' || github.event.workflow_run.conclusion == 'success' }}

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: pip install -r scripts/requirements.txt

      - name: Fetch tweets
        env:
          X_BEARER_TOKEN: ${{ secrets.X_BEARER_TOKEN }}
        run: cd scripts/dify_sync && python3 fetch_tweets.py
        continue-on-error: true

      - name: Fetch Google Sheets
        env:
          GOOGLE_SERVICE_ACCOUNT_KEY: ${{ secrets.GOOGLE_SERVICE_ACCOUNT_KEY }}
          SHEET_ID_MACRO: ${{ secrets.SHEET_ID_MACRO }}
          SHEET_ID_POSITIONS: ${{ secrets.SHEET_ID_POSITIONS }}
          SHEET_ID_DATASOURCES: ${{ secrets.SHEET_ID_DATASOURCES }}
          SHEET_ID_BETA: ${{ secrets.SHEET_ID_BETA }}
          SHEET_ID_COMMUNITY: ${{ secrets.SHEET_ID_COMMUNITY }}
        run: cd scripts/dify_sync && python3 fetch_sheets.py
        continue-on-error: true

      - name: Sync to vector store
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          VECTOR_STORE_ID: ${{ secrets.VECTOR_STORE_ID }}
        run: cd scripts/dify_sync && python3 sync_vector_store.py

      - name: Commit data changes
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/
          git diff --staged --quiet || git commit -m "chore: sync knowledge base data $(date +%Y-%m-%d)"
          git push
```

**Step 2: Commit**

```bash
git add .github/workflows/daily-sync-kb.yml
git commit -m "feat: add daily knowledge base sync GitHub Action"
```

---

### Task 7: Add Sheet IDs as GitHub Secrets

This is a manual step. The user needs to:

1. Open each Google Sheet in a browser
2. Copy the sheet ID from the URL: `https://docs.google.com/spreadsheets/d/{THIS_IS_THE_ID}/edit`
3. Go to GitHub repo → Settings → Secrets → Actions
4. Add each secret:
   - `SHEET_ID_MACRO` — from 投資talk君-總經公告
   - `SHEET_ID_POSITIONS` — from 投資Talk君-持倉績效 ytd
   - `SHEET_ID_DATASOURCES` — from 投資talk君-資料來源
   - `SHEET_ID_BETA` — from 投資talk君-持倉Beta
   - `SHEET_ID_COMMUNITY` — from 爬蟲-投資talk君2025文章
   - `X_BEARER_TOKEN` — from local `.env`
   - `VECTOR_STORE_ID` — from local `.env`

---

### Task 8: End-to-end test via manual workflow dispatch

**Step 1: Push all changes to GitHub**

```bash
git push origin main
```

**Step 2: Trigger the workflow manually**

Go to GitHub repo → Actions → "Daily Sync Knowledge Base" → Run workflow

**Step 3: Verify**

- Check the workflow run completes successfully
- Check each step's log output for expected counts
- Verify `data/tweets/tweets.json` was updated
- Verify `data/sheets/*.json` files were created
- Test the chat bot — ask a question that would require Google Sheets data to answer

---

## Summary of All Files

| Action | File |
|--------|------|
| Modify | `scripts/dify_sync/config.py` — add Sheets config |
| Modify | `scripts/requirements.txt` — add google-auth deps |
| Create | `scripts/dify_sync/fetch_sheets.py` — Google Sheets fetcher |
| Create | `scripts/dify_sync/sync_vector_store.py` — sync orchestrator |
| Create | `data/docs/app-guide.md` — placeholder app guide |
| Create | `.github/workflows/daily-sync-kb.yml` — daily sync workflow |
| Manual | Add 7 GitHub secrets (5 sheet IDs + X token + vector store ID) |
