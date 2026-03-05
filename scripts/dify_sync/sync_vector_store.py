#!/usr/bin/env python3
"""Orchestrate: convert all sources to Markdown → diff → upload to vector store."""

import json
import os
import sys
import tempfile
from datetime import datetime

from openai import OpenAI

from config import (
    VECTOR_STORE_ID, SUMMARIES_DIR, TWEETS_FILE,
    SHEETS_DIR, DOCS_DIR
)
from convert_and_upload import summary_to_markdown, tweets_to_markdown_by_week

# Verify API key is available before proceeding
api_key = os.getenv("OPENAI_API_KEY", "")
if not api_key:
    print("Error: OPENAI_API_KEY not set", file=sys.stderr)
    sys.exit(1)
print(f"OPENAI_API_KEY set (length={len(api_key)})", file=sys.stderr)
print(f"VECTOR_STORE_ID={VECTOR_STORE_ID or '(empty)'}", file=sys.stderr)

client = OpenAI(api_key=api_key)

VECTOR_STORE_NAME = "投資Talk君-知識庫"


def get_or_create_vector_store():
    """Get existing vector store or create a new one."""
    if VECTOR_STORE_ID:
        try:
            vs = client.vector_stores.retrieve(VECTOR_STORE_ID)
            print(f"Using existing vector store: {vs.id}", file=sys.stderr)
            return vs
        except Exception as e:
            print(f"Warning: Could not retrieve store {VECTOR_STORE_ID}: {e}",
                  file=sys.stderr)

    vs = client.vector_stores.create(name=VECTOR_STORE_NAME)
    print(f"Created new vector store: {vs.id}", file=sys.stderr)
    print(f"  → Add to .env: VECTOR_STORE_ID={vs.id}", file=sys.stderr)
    return vs


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


def convert_summaries():
    """Convert YouTube summaries to Markdown."""
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
    """Convert tweets to weekly Markdown files."""
    if not os.path.exists(TWEETS_FILE):
        return []
    with open(TWEETS_FILE, 'r', encoding='utf-8') as f:
        tweets = json.load(f)
    if not tweets:
        return []
    return tweets_to_markdown_by_week(tweets)


def convert_sheets():
    """Convert Google Sheets JSON to Markdown."""
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
            lines.append("| " + " | ".join(headers) + " |")
            lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
            for row in rows:
                vals = [str(row.get(h, "")).replace("|", "\\|").replace("\n", " ") for h in headers]
                lines.append("| " + " | ".join(vals) + " |")

        md_filename = f"sheet-{slug}-latest.md"
        results.append((md_filename, "\n".join(lines)))

    return results


def convert_app_guide():
    """Read app guide Markdown if it exists."""
    guide_path = os.path.join(DOCS_DIR, "app-guide.md")
    if not os.path.exists(guide_path):
        return []
    with open(guide_path, 'r', encoding='utf-8') as f:
        content = f.read()
    if not content.strip():
        return []
    return [("app-guide.md", content)]


def sync(dry_run=False):
    """Main sync: convert all → diff → upload new/changed → delete removed."""
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
            # Always re-upload sheets (daily data) and tweet files
            to_upload.append((name, content, "update"))
            to_delete.append((name, existing[name]))

    # Files in vector store but not locally → delete
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
