#!/usr/bin/env python3
"""Rebuild data/index.json from all summary files."""

import json
import os

SUMMARIES_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'summaries')
INDEX_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'index.json')


def build_index():
    """Scan all summary JSONs and build lightweight index."""
    entries = []

    for filename in sorted(os.listdir(SUMMARIES_DIR), reverse=True):
        if not filename.endswith('.json'):
            continue

        filepath = os.path.join(SUMMARIES_DIR, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: skipping {filename}: {e}")
            continue

        entry = {
            'id': data.get('id', ''),
            'title': data.get('title', ''),
            'publishedAt': data.get('publishedAt', ''),
            'channelName': data.get('channelName', ''),
            'duration': data.get('duration', 0),
            'thumbnailUrl': data.get('thumbnailUrl', ''),
            'videoUrl': data.get('videoUrl', ''),
            'tags': data.get('summary', {}).get('zh-Hans', {}).get('tags', []),
            'tickers': [t['symbol'] for t in data.get('tickers', [])]
        }
        entries.append(entry)

    entries.sort(key=lambda x: x.get('publishedAt', ''), reverse=True)

    with open(INDEX_PATH, 'w', encoding='utf-8') as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)

    print(f"Built index with {len(entries)} entries")
    return entries


if __name__ == '__main__':
    build_index()
