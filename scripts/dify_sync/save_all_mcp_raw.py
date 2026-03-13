#!/usr/bin/env python3
"""Save all MCP data fetched in the current session.

Run this from the talk_library root directory.
It re-fetches data via the MCP API HTTP endpoint or loads from tool result files.
"""

import json
import os
import subprocess
import sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
RAW_DIR = os.path.join(ROOT_DIR, 'data', 'mcp', 'raw')
os.makedirs(RAW_DIR, exist_ok=True)


def save_json(filename, data):
    """Save parsed result data as JSON."""
    filepath = os.path.join(RAW_DIR, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    total = data.get('total', 0)
    print(f"  Saved {filepath}: {total} items")


def main():
    """
    This script expects pre-saved JSON files in data/mcp/raw/.
    The actual MCP API calls are made via Claude Code MCP tools,
    and the results are saved here by companion scripts.

    Validates that all expected files exist.
    """
    expected_files = [
        "grouparticle-board-10918.json",
        "grouparticle-board-10919.json",
        "grouparticle-board-10921.json",
        "chatroomarticle-board-10918.json",
        "chatroomarticle-board-10919.json",
        "chatroomarticle-board-10921.json",
        "chatroomarticle-board-12784.json",
    ]

    missing = []
    total_articles = 0
    for fname in expected_files:
        fpath = os.path.join(RAW_DIR, fname)
        if os.path.exists(fpath):
            with open(fpath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            count = data.get('total', 0)
            total_articles += count
            print(f"  OK: {fname} ({count} items)")
        else:
            missing.append(fname)
            print(f"  MISSING: {fname}")

    if missing:
        print(f"\n{len(missing)} files missing. Run MCP fetch first.")
        return False

    print(f"\nAll files present. Total: {total_articles} articles")
    return True


if __name__ == "__main__":
    main()
