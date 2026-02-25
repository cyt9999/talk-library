#!/usr/bin/env python3
"""
投資Talk君 Local Server

- Serves the static site
- Watches data/uploads/ folder for new audio/video files
- Auto-processes: transcribe -> summarize -> build index -> sync to site

Usage:
  python upload_server.py [port]

To add content:
  1. Drop audio/video files into data/uploads/
  2. Server auto-detects and processes them
  3. Summaries appear on the site after processing
"""

import json
import os
import sys
import time
import shutil
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SITE_DIR = os.path.join(PROJECT_ROOT, 'site')
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
UPLOADS_DIR = os.path.join(DATA_DIR, 'uploads')
SUMMARIES_DIR = os.path.join(DATA_DIR, 'summaries')

WATCH_EXTENSIONS = {'.mp3', '.wav', '.m4a', '.mp4', '.webm', '.ogg', '.flac'}
POLL_INTERVAL = 5  # seconds

sys.path.insert(0, os.path.dirname(__file__))
from transcribe import transcribe_file
from summarize import create_summary, save_summary
from build_index import build_index


def sync_data_to_site():
    """Copy data/ into site/data/ for serving."""
    site_data = os.path.join(SITE_DIR, 'data')
    if os.path.exists(site_data):
        shutil.rmtree(site_data)
    shutil.copytree(DATA_DIR, site_data)


def process_file(filepath, filename):
    """Process a single uploaded file."""
    name_without_ext = os.path.splitext(filename)[0]
    video_id = name_without_ext.replace(' ', '_')

    print(f"  [1/3] Transcribing {filename}...")
    transcript = transcribe_file(filepath)

    print(f"  [2/3] Summarizing with GPT-4o...")
    video_info = {
        'videoId': video_id,
        'title': name_without_ext,
        'channelName': '手動上傳',
        'channelId': 'manual',
        'videoUrl': '',
        'thumbnailUrl': '',
        'publishedAt': datetime.now().strftime('%Y-%m-%d')
    }
    summary = create_summary(video_info, transcript)
    save_summary(summary, SUMMARIES_DIR)

    print(f"  [3/3] Rebuilding index & syncing...")
    build_index()
    sync_data_to_site()

    # Remove processed file
    os.remove(filepath)
    print(f"  Done! Summary saved for: {name_without_ext}\n")


def watch_uploads():
    """Poll data/uploads/ folder for new files and auto-process them."""
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    seen_files = set()

    # On startup, note existing files (don't re-process)
    for f in os.listdir(UPLOADS_DIR):
        if not f.startswith('.'):
            seen_files.add(f)

    print(f"Watching folder: {UPLOADS_DIR}")
    print(f"  Drop audio/video files here to auto-process.\n")

    while True:
        try:
            current_files = set()
            for f in os.listdir(UPLOADS_DIR):
                if f.startswith('.'):
                    continue
                ext = os.path.splitext(f)[1].lower()
                if ext in WATCH_EXTENSIONS:
                    current_files.add(f)

            new_files = current_files - seen_files
            for filename in sorted(new_files):
                filepath = os.path.join(UPLOADS_DIR, filename)

                # Wait a moment to ensure file is fully written
                size1 = os.path.getsize(filepath)
                time.sleep(2)
                size2 = os.path.getsize(filepath)
                if size1 != size2:
                    continue  # File still being written

                print(f"\nNew file detected: {filename}")
                try:
                    process_file(filepath, filename)
                    seen_files.add(filename)
                except Exception as e:
                    print(f"  Error processing {filename}: {e}\n")
                    seen_files.add(filename)  # Don't retry endlessly

            # Track removed files too
            seen_files = seen_files & (current_files | {f for f in seen_files if f not in current_files})

        except Exception as e:
            print(f"Watch error: {e}")

        time.sleep(POLL_INTERVAL)


class SiteHandler(SimpleHTTPRequestHandler):
    """Serves static files from site/ directory."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=SITE_DIR, **kwargs)

    def log_message(self, format, *args):
        pass  # Suppress request logs to keep console clean for watcher output


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8081

    # Sync data on startup
    sync_data_to_site()

    # Start HTTP server in background
    server = HTTPServer(('0.0.0.0', port), SiteHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    print("=" * 56)
    print("  投資Talk君 Local Server")
    print("=" * 56)
    print(f"\n  Site:    http://localhost:{port}")
    print(f"  Uploads: {UPLOADS_DIR}")
    print(f"\n  Drop files into the uploads folder to auto-process.")
    print(f"  Supported: {', '.join(sorted(WATCH_EXTENSIONS))}")
    print(f"\n  Press Ctrl+C to stop.\n")
    print("-" * 56)

    # Run folder watcher in main thread
    try:
        watch_uploads()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        server.server_close()


if __name__ == '__main__':
    main()
