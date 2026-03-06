#!/usr/bin/env python3
"""One-time repair script: fix incorrect publishedAt dates in summary files.

13 videos got publishedAt=2026-03-03 (the pipeline run date) instead of their
actual YouTube upload dates. This script re-fetches the real dates via yt-dlp,
updates the JSON files, renames them, and rebuilds the index.
"""

import json
import os
import subprocess
import sys

SUMMARIES_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'summaries')
WRONG_DATE = '2026-03-03'


def fetch_upload_date(video_id):
    """Use yt-dlp to get the actual upload date for a video."""
    cmd = [
        sys.executable, '-m', 'yt_dlp',
        '--print', '%(upload_date)s',
        '--no-download',
        f'https://www.youtube.com/watch?v={video_id}'
    ]
    result = subprocess.run(cmd, capture_output=True, encoding='utf-8', timeout=30)
    if result.returncode != 0:
        print(f"  Warning: yt-dlp failed for {video_id}: {result.stderr.strip()}", file=sys.stderr)
        return None

    raw = result.stdout.strip()
    if raw and raw != 'NA' and len(raw) == 8:
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    return None


def fix_dates():
    """Scan summaries, fix wrong dates, rename files."""
    fixed = 0
    skipped = 0

    for filename in sorted(os.listdir(SUMMARIES_DIR)):
        if not filename.endswith('.json') or not filename.startswith(WRONG_DATE):
            continue

        filepath = os.path.join(SUMMARIES_DIR, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        video_id = data.get('videoId', '')
        if not video_id:
            print(f"  Skipping {filename}: no videoId", file=sys.stderr)
            skipped += 1
            continue

        print(f"Fetching date for {video_id} ({data.get('title', '')[:40]}...) ", file=sys.stderr, end='')
        real_date = fetch_upload_date(video_id)

        if not real_date:
            print("FAILED - keeping original", file=sys.stderr)
            skipped += 1
            continue

        if real_date == WRONG_DATE:
            print(f"already correct ({real_date})", file=sys.stderr)
            continue

        # Update JSON
        data['publishedAt'] = real_date
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # Rename file
        new_filename = f"{real_date}-{video_id}.json"
        new_filepath = os.path.join(SUMMARIES_DIR, new_filename)
        os.rename(filepath, new_filepath)

        print(f"-> {real_date} (renamed to {new_filename})", file=sys.stderr)
        fixed += 1

    print(f"\nDone: {fixed} fixed, {skipped} skipped", file=sys.stderr)
    return fixed


def rebuild_index():
    """Run build_index.py to regenerate data/index.json."""
    build_script = os.path.join(os.path.dirname(__file__), 'build_index.py')
    subprocess.run([sys.executable, build_script], check=True)


if __name__ == '__main__':
    count = fix_dates()
    if count > 0:
        print("\nRebuilding index...", file=sys.stderr)
        rebuild_index()
