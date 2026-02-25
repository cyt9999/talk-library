# 投資Talk君 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Use superpowers:frontend-design for Task 4 (UI implementation).

**Goal:** Build an automated investment content summarization site hosted on GitHub Pages, loaded in CMoney app WebView.

**Architecture:** GitHub Actions daily cron fetches new YouTube videos, transcribes via Whisper API, summarizes via Claude API, commits JSON data to repo. Static vanilla HTML/CSS/JS frontend serves summaries with search, filter, and bookmarks.

**Tech Stack:** Python 3.x (scripts), vanilla HTML/CSS/JS (frontend), GitHub Actions (CI), OpenAI Whisper API, Anthropic Claude API, GitHub Pages (hosting).

---

### Task 1: Project Scaffolding

**Files:**
- Create: `data/channels.json`
- Create: `data/summaries/.gitkeep`
- Create: `data/uploads/.gitkeep`
- Create: `data/index.json`
- Create: `scripts/requirements.txt`
- Create: `.gitignore`

**Step 1: Create directory structure**

```bash
mkdir -p data/summaries data/uploads scripts site/css site/js docs/plans .github/workflows
```

**Step 2: Create .gitignore**

```
# Python
__pycache__/
*.pyc
.env
venv/

# OS
.DS_Store
Thumbs.db

# Temp audio files
scripts/*.mp3
scripts/*.wav
scripts/*.m4a
data/uploads/*.mp3
data/uploads/*.wav
data/uploads/*.m4a
data/uploads/*.mp4

# IDE
.vscode/
.idea/
```

**Step 3: Create channels.json**

```json
[
  {
    "id": "talk_yt",
    "name": "投资TALK君",
    "rssUrl": "https://www.youtube.com/@yttalkjun"
  }
]
```

**Step 4: Create empty index.json**

```json
[]
```

**Step 5: Create requirements.txt**

```
yt-dlp>=2024.0.0
openai>=1.0.0
anthropic>=0.40.0
feedparser>=6.0.0
```

**Step 6: Create .gitkeep files**

```bash
touch data/summaries/.gitkeep data/uploads/.gitkeep
```

**Step 7: Commit**

```bash
git init
git add .
git commit -m "chore: scaffold project structure"
```

---

### Task 2: Fetch New Videos Script

**Files:**
- Create: `scripts/fetch_new_videos.py`

**Step 1: Write fetch_new_videos.py**

This script:
1. Reads `data/channels.json` for channel list
2. Fetches each channel's RSS feed (YouTube provides RSS at `https://www.youtube.com/feeds/videos.xml?channel_id=CHANNEL_ID`)
3. Compares video IDs against existing files in `data/summaries/`
4. Outputs a JSON list of new videos to process

```python
#!/usr/bin/env python3
"""Fetch new videos from YouTube channels that haven't been summarized yet."""

import json
import os
import sys
import re
import feedparser
import urllib.request

CHANNELS_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'channels.json')
SUMMARIES_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'summaries')


def get_channel_id_from_handle(handle_url):
    """Resolve a YouTube handle URL to a channel ID by fetching the page."""
    try:
        req = urllib.request.Request(handle_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
        match = re.search(r'"channelId":"(UC[^"]+)"', html)
        if match:
            return match.group(1)
    except Exception as e:
        print(f"Warning: Could not resolve handle {handle_url}: {e}", file=sys.stderr)
    return None


def get_rss_url(channel_config):
    """Get the RSS feed URL for a channel."""
    rss_url = channel_config['rssUrl']
    # If it's already a feeds URL, use it directly
    if 'feeds/videos.xml' in rss_url:
        return rss_url
    # If it's a handle URL like https://www.youtube.com/@yttalkjun
    if '/@' in rss_url:
        channel_id = get_channel_id_from_handle(rss_url)
        if channel_id:
            return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        return None
    # If it's a channel URL with ID
    if '/channel/' in rss_url:
        channel_id = rss_url.split('/channel/')[-1].strip('/')
        return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    return None


def get_existing_video_ids():
    """Get set of video IDs that already have summaries."""
    ids = set()
    if not os.path.exists(SUMMARIES_DIR):
        return ids
    for filename in os.listdir(SUMMARIES_DIR):
        if filename.endswith('.json'):
            try:
                with open(os.path.join(SUMMARIES_DIR, filename), 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if 'videoId' in data:
                        ids.add(data['videoId'])
            except (json.JSONDecodeError, KeyError):
                continue
    return ids


def fetch_new_videos():
    """Fetch RSS feeds and return list of new videos."""
    with open(CHANNELS_PATH, 'r', encoding='utf-8') as f:
        channels = json.load(f)

    existing_ids = get_existing_video_ids()
    new_videos = []

    for channel in channels:
        rss_url = get_rss_url(channel)
        if not rss_url:
            print(f"Warning: Could not determine RSS URL for {channel['name']}", file=sys.stderr)
            continue

        print(f"Fetching RSS for {channel['name']}: {rss_url}", file=sys.stderr)
        feed = feedparser.parse(rss_url)

        for entry in feed.entries:
            video_id = entry.get('yt_videoid', '')
            if not video_id:
                # Try to extract from link
                link = entry.get('link', '')
                if 'watch?v=' in link:
                    video_id = link.split('watch?v=')[-1].split('&')[0]

            if video_id and video_id not in existing_ids:
                new_videos.append({
                    'videoId': video_id,
                    'title': entry.get('title', ''),
                    'publishedAt': entry.get('published', ''),
                    'channelName': channel['name'],
                    'channelId': channel['id'],
                    'videoUrl': f"https://www.youtube.com/watch?v={video_id}",
                    'thumbnailUrl': f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
                })

    return new_videos


if __name__ == '__main__':
    videos = fetch_new_videos()
    print(json.dumps(videos, ensure_ascii=False, indent=2))
    print(f"\nFound {len(videos)} new video(s)", file=sys.stderr)
```

**Step 2: Test locally**

```bash
cd scripts
pip install -r requirements.txt
python fetch_new_videos.py
```

Expected: JSON array of videos from the 投资TALK君 channel that don't have summaries yet.

**Step 3: Commit**

```bash
git add scripts/fetch_new_videos.py
git commit -m "feat: add fetch new videos script"
```

---

### Task 3: Transcribe Script

**Files:**
- Create: `scripts/transcribe.py`

**Step 1: Write transcribe.py**

This script:
1. Takes a video URL or local file path as input
2. Downloads audio via yt-dlp (if URL)
3. Sends to OpenAI Whisper API for transcription
4. Returns timestamped transcript

```python
#!/usr/bin/env python3
"""Transcribe video/audio using OpenAI Whisper API."""

import json
import os
import sys
import subprocess
import tempfile
from openai import OpenAI

client = OpenAI()


def download_audio(video_url, output_dir):
    """Download audio from YouTube video using yt-dlp."""
    output_path = os.path.join(output_dir, '%(id)s.%(ext)s')
    cmd = [
        'yt-dlp',
        '-x',                          # Extract audio only
        '--audio-format', 'mp3',       # Convert to mp3
        '--audio-quality', '5',        # Medium quality (smaller file)
        '-o', output_path,
        video_url
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {result.stderr}")

    # Find the downloaded file
    for f in os.listdir(output_dir):
        if f.endswith('.mp3'):
            return os.path.join(output_dir, f)
    raise FileNotFoundError("No audio file found after download")


def transcribe_audio(audio_path):
    """Transcribe audio file using Whisper API with timestamps."""
    with open(audio_path, 'rb') as f:
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            language="zh",
            response_format="verbose_json",
            timestamp_granularities=["segment"]
        )

    segments = []
    for seg in response.segments:
        segments.append({
            'start': round(seg['start']),
            'end': round(seg['end']),
            'text': seg['text'].strip()
        })

    return {
        'text': response.text,
        'segments': segments,
        'duration': round(response.duration) if hasattr(response, 'duration') else None
    }


def transcribe_video(video_url):
    """Download and transcribe a YouTube video."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        print(f"Downloading audio from {video_url}...", file=sys.stderr)
        audio_path = download_audio(video_url, tmp_dir)
        print(f"Transcribing {audio_path}...", file=sys.stderr)
        return transcribe_audio(audio_path)


def transcribe_file(file_path):
    """Transcribe a local audio/video file."""
    print(f"Transcribing {file_path}...", file=sys.stderr)
    return transcribe_audio(file_path)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python transcribe.py <video_url_or_file_path>", file=sys.stderr)
        sys.exit(1)

    source = sys.argv[1]
    if source.startswith('http'):
        result = transcribe_video(source)
    else:
        result = transcribe_file(source)

    print(json.dumps(result, ensure_ascii=False, indent=2))
```

**Step 2: Test locally** (requires OPENAI_API_KEY env var)

```bash
export OPENAI_API_KEY="your-key"
python scripts/transcribe.py "https://www.youtube.com/watch?v=VIDEO_ID"
```

Expected: JSON with `text`, `segments[]` (with start/end timestamps), and `duration`.

**Step 3: Commit**

```bash
git add scripts/transcribe.py
git commit -m "feat: add transcription script using Whisper API"
```

---

### Task 4: Summarize Script

**Files:**
- Create: `scripts/summarize.py`

**Step 1: Write summarize.py**

This script:
1. Takes a transcript JSON and video metadata as input
2. Sends to Claude API with a structured prompt
3. Extracts: key points with timestamps, paragraph summary, tags, tickers with sentiment and timestamp ranges
4. Outputs both 簡體 and 繁體 versions

```python
#!/usr/bin/env python3
"""Summarize transcript using Claude API. Extract tickers, sentiment, timestamps."""

import json
import os
import sys
from datetime import datetime, timezone
import anthropic

client = anthropic.Anthropic()

SUMMARY_PROMPT = """你是一位专业的美股投资内容分析师。请分析以下视频转录文本，并生成结构化摘要。

## 转录文本
{transcript}

## 要求

请以JSON格式输出以下内容：

1. **keyPoints**: 关键要点列表（5-10个），每个要点包含：
   - `timestamp`: 对应转录文本中最相关的时间点（秒数）
   - `text`: 要点内容（简体中文，1-2句话）

2. **paragraph**: 整体总结段落（简体中文，100-200字）

3. **tags**: 内容标签列表（如：美股、联准会、半导体、AI等）

4. **tickers**: 提到的美股代码列表，每个包含：
   - `symbol`: 股票代码（如 NVDA, AAPL, TSLA）
   - `name`: 中文名称
   - `sentiment`: 视频对该股票的态度（"bullish" / "bearish" / "neutral"）
   - `mentions`: 提到该股票的时间段列表，每段包含：
     - `start`: 开始时间（秒）
     - `end`: 结束时间（秒）
     - `context`: 该段讨论的简短描述

请只输出JSON，不要包含其他文字。确保JSON格式正确。
"""

CONVERT_PROMPT = """请将以下简体中文JSON内容转换为繁体中文。只转换中文文字，不要修改JSON结构、英文内容、数字或代码。请只输出JSON。

{json_content}
"""


def summarize_transcript(transcript_text, segments):
    """Send transcript to Claude API for summarization."""
    # Build transcript with timestamps for context
    timestamped_text = ""
    for seg in segments:
        minutes = seg['start'] // 60
        seconds = seg['start'] % 60
        timestamped_text += f"[{minutes:02d}:{seconds:02d}] {seg['text']}\n"

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": SUMMARY_PROMPT.format(transcript=timestamped_text)
        }]
    )

    result_text = response.content[0].text.strip()
    # Remove markdown code fences if present
    if result_text.startswith('```'):
        result_text = result_text.split('\n', 1)[1]
        if result_text.endswith('```'):
            result_text = result_text.rsplit('```', 1)[0]

    return json.loads(result_text)


def convert_to_traditional(simplified_data):
    """Convert simplified Chinese summary to traditional Chinese."""
    json_str = json.dumps(simplified_data, ensure_ascii=False, indent=2)

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": CONVERT_PROMPT.format(json_content=json_str)
        }]
    )

    result_text = response.content[0].text.strip()
    if result_text.startswith('```'):
        result_text = result_text.split('\n', 1)[1]
        if result_text.endswith('```'):
            result_text = result_text.rsplit('```', 1)[0]

    return json.loads(result_text)


def create_summary(video_info, transcript):
    """Create full summary JSON from video info and transcript."""
    print(f"Summarizing: {video_info['title']}...", file=sys.stderr)

    # Get simplified Chinese summary + tickers
    zh_hans_result = summarize_transcript(transcript['text'], transcript['segments'])

    # Convert to traditional Chinese
    print("Converting to Traditional Chinese...", file=sys.stderr)
    zh_hant_data = {
        'keyPoints': zh_hans_result['keyPoints'],
        'paragraph': zh_hans_result['paragraph'],
        'tags': zh_hans_result['tags']
    }
    zh_hant_result = convert_to_traditional(zh_hant_data)

    # Build final summary object
    summary = {
        'id': video_info['videoId'],
        'videoId': video_info['videoId'],
        'source': 'youtube',
        'channelName': video_info['channelName'],
        'title': video_info['title'],
        'publishedAt': video_info.get('publishedAt', ''),
        'summarizedAt': datetime.now(timezone.utc).isoformat(),
        'duration': transcript.get('duration', 0),
        'thumbnailUrl': video_info.get('thumbnailUrl', ''),
        'videoUrl': video_info.get('videoUrl', ''),
        'summary': {
            'zh-Hans': {
                'keyPoints': zh_hans_result['keyPoints'],
                'paragraph': zh_hans_result['paragraph'],
                'tags': zh_hans_result['tags']
            },
            'zh-Hant': {
                'keyPoints': zh_hant_result['keyPoints'],
                'paragraph': zh_hant_result['paragraph'],
                'tags': zh_hant_result['tags']
            }
        },
        'tickers': zh_hans_result.get('tickers', [])
    }

    return summary


def save_summary(summary, output_dir):
    """Save summary JSON to data/summaries/."""
    date_str = summary['publishedAt'][:10] if summary['publishedAt'] else datetime.now().strftime('%Y-%m-%d')
    filename = f"{date_str}-{summary['videoId']}.json"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"Saved: {filepath}", file=sys.stderr)
    return filepath


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python summarize.py <video_info.json> <transcript.json>", file=sys.stderr)
        sys.exit(1)

    with open(sys.argv[1], 'r', encoding='utf-8') as f:
        video_info = json.load(f)
    with open(sys.argv[2], 'r', encoding='utf-8') as f:
        transcript = json.load(f)

    summaries_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'summaries')
    summary = create_summary(video_info, transcript)
    save_summary(summary, summaries_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
```

**Step 2: Commit**

```bash
git add scripts/summarize.py
git commit -m "feat: add summarization script using Claude API"
```

---

### Task 5: Build Index Script

**Files:**
- Create: `scripts/build_index.py`

**Step 1: Write build_index.py**

```python
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

    # Sort by publishedAt descending
    entries.sort(key=lambda x: x.get('publishedAt', ''), reverse=True)

    with open(INDEX_PATH, 'w', encoding='utf-8') as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)

    print(f"Built index with {len(entries)} entries")
    return entries


if __name__ == '__main__':
    build_index()
```

**Step 2: Commit**

```bash
git add scripts/build_index.py
git commit -m "feat: add build index script"
```

---

### Task 6: Pipeline Runner Script

**Files:**
- Create: `scripts/run_pipeline.py`

**Step 1: Write run_pipeline.py**

Orchestrates the full pipeline: fetch → transcribe → summarize → build index.

```python
#!/usr/bin/env python3
"""Run the full pipeline: fetch new videos → transcribe → summarize → build index."""

import json
import os
import sys

from fetch_new_videos import fetch_new_videos
from transcribe import transcribe_video, transcribe_file
from summarize import create_summary, save_summary
from build_index import build_index

SUMMARIES_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'summaries')
UPLOADS_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'uploads')


def process_new_youtube_videos():
    """Fetch and process new videos from YouTube channels."""
    videos = fetch_new_videos()
    print(f"Found {len(videos)} new video(s) to process")

    for video in videos:
        try:
            print(f"\nProcessing: {video['title']}")
            transcript = transcribe_video(video['videoUrl'])
            summary = create_summary(video, transcript)
            save_summary(summary, SUMMARIES_DIR)
            print(f"Done: {video['title']}")
        except Exception as e:
            print(f"Error processing {video['title']}: {e}", file=sys.stderr)
            continue

    return len(videos)


def process_uploads():
    """Process any files in data/uploads/."""
    if not os.path.exists(UPLOADS_DIR):
        return 0

    processed = 0
    for filename in os.listdir(UPLOADS_DIR):
        if filename.startswith('.'):
            continue
        if not filename.endswith(('.mp3', '.wav', '.m4a', '.mp4', '.webm')):
            continue

        filepath = os.path.join(UPLOADS_DIR, filename)
        name_without_ext = os.path.splitext(filename)[0]

        try:
            print(f"\nProcessing upload: {filename}")
            transcript = transcribe_file(filepath)
            video_info = {
                'videoId': name_without_ext,
                'title': name_without_ext,
                'channelName': '手動上傳',
                'channelId': 'manual',
                'videoUrl': '',
                'thumbnailUrl': '',
                'publishedAt': ''
            }
            summary = create_summary(video_info, transcript)
            save_summary(summary, SUMMARIES_DIR)

            # Remove processed file
            os.remove(filepath)
            print(f"Done: {filename}")
            processed += 1
        except Exception as e:
            print(f"Error processing {filename}: {e}", file=sys.stderr)
            continue

    return processed


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'all'

    if mode in ('youtube', 'all'):
        process_new_youtube_videos()

    if mode in ('uploads', 'all'):
        process_uploads()

    build_index()
    print("\nPipeline complete!")
```

**Step 2: Commit**

```bash
git add scripts/run_pipeline.py
git commit -m "feat: add pipeline runner script"
```

---

### Task 7: GitHub Actions Workflows

**Files:**
- Create: `.github/workflows/daily-summarize.yml`
- Create: `.github/workflows/manual-upload.yml`

**Step 1: Write daily-summarize.yml**

```yaml
name: Daily Summarize

on:
  schedule:
    # Run daily at 00:00 UTC (08:00 UTC+8)
    - cron: '0 0 * * *'
  workflow_dispatch:

permissions:
  contents: write

jobs:
  summarize:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: |
          pip install -r scripts/requirements.txt
          pip install yt-dlp

      - name: Install ffmpeg
        run: sudo apt-get update && sudo apt-get install -y ffmpeg

      - name: Run pipeline (YouTube)
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: python scripts/run_pipeline.py youtube

      - name: Commit and push
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/
          git diff --staged --quiet || git commit -m "chore: auto-summarize new videos $(date +%Y-%m-%d)"
          git push
```

**Step 2: Write manual-upload.yml**

```yaml
name: Process Uploads

on:
  push:
    paths:
      - 'data/uploads/**'
  workflow_dispatch:

permissions:
  contents: write

jobs:
  process:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: |
          pip install -r scripts/requirements.txt

      - name: Install ffmpeg
        run: sudo apt-get update && sudo apt-get install -y ffmpeg

      - name: Run pipeline (uploads)
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: python scripts/run_pipeline.py uploads

      - name: Commit and push
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/
          git diff --staged --quiet || git commit -m "chore: process uploaded content $(date +%Y-%m-%d)"
          git push
```

**Step 3: Commit**

```bash
git add .github/workflows/
git commit -m "feat: add GitHub Actions workflows for daily summarize and uploads"
```

---

### Task 8: Sample Data

**Files:**
- Create: `data/summaries/2026-02-24-sample001.json`

**Step 1: Create a realistic sample summary for frontend development**

Create a sample JSON file matching the data model spec so the frontend can be developed and tested without waiting for the real pipeline. Use realistic US stock investment content data.

**Step 2: Run build_index.py to generate index.json from sample**

```bash
python scripts/build_index.py
```

**Step 3: Commit**

```bash
git add data/
git commit -m "feat: add sample data for frontend development"
```

---

### Task 9: Frontend — UI Design & Implementation

> **REQUIRED SUB-SKILL:** Use superpowers:frontend-design for this task.

**Files:**
- Create: `site/index.html` — Home page (summary list, search, filters)
- Create: `site/summary.html` — Summary detail page
- Create: `site/bookmarks.html` — Bookmarks page
- Create: `site/css/style.css` — All styles
- Create: `site/js/app.js` — Main app logic, routing, language toggle
- Create: `site/js/search.js` — Client-side search and filter
- Create: `site/js/bookmarks.js` — localStorage bookmark manager

**Design requirements:**
- Mobile-first (320px-428px primary viewport, loaded in CMoney WebView)
- Investment/finance aesthetic — professional but approachable
- 簡體/繁體 toggle in header
- Summary cards with thumbnail, title, date, tag pills, ticker pills (colored by sentiment)
- Detail page with YouTube embed, timestamped key points (clickable), ticker cards
- Client-side search over index.json (title, tags, tickers)
- Bookmark to localStorage
- Load data from `../data/index.json` and `../data/summaries/{id}.json`

**Step 1: Design and implement all HTML pages with CSS**

Use the frontend-design skill to create a distinctive, polished mobile-first UI.

**Step 2: Implement app.js — core logic**

- Language state management (localStorage)
- Load index.json on home page
- Render summary cards
- Navigate to detail page via query param (`summary.html?id=xxx`)
- Load individual summary JSON on detail page
- YouTube iframe API integration for timestamp jumping

**Step 3: Implement search.js — search & filter**

- Full-text search over title, tags, tickers
- Filter by tag chips
- Filter by ticker
- Date range filter
- Debounced input handler

**Step 4: Implement bookmarks.js — bookmark manager**

- Add/remove bookmark (store summary ID + title + date in localStorage)
- Check if current summary is bookmarked
- List all bookmarks on bookmarks page
- Remove individual bookmarks

**Step 5: Test in browser**

Open `site/index.html` locally, verify:
- Sample data renders correctly
- Search filters work
- Bookmark add/remove works
- Detail page shows summary with clickable timestamps
- 簡體/繁體 toggle switches text

**Step 6: Commit**

```bash
git add site/
git commit -m "feat: add frontend UI with search, filters, and bookmarks"
```

---

### Task 10: GitHub Pages Configuration

**Files:**
- Modify: repository settings (via GitHub)

**Step 1: Configure GitHub Pages to serve from `/site` directory**

Option A: Add a `_config.yml` or use GitHub UI to set source to `main` branch, `/site` folder.

Option B: Create a simple deploy workflow:

```yaml
# .github/workflows/deploy-pages.yml
name: Deploy to GitHub Pages

on:
  push:
    branches: [main]
    paths:
      - 'site/**'
      - 'data/**'

permissions:
  pages: write
  id-token: write

jobs:
  deploy:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Copy data into site
        run: cp -r data site/data

      - name: Setup Pages
        uses: actions/configure-pages@v4

      - name: Upload artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: site

      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
```

**Step 2: Commit**

```bash
git add .github/workflows/deploy-pages.yml
git commit -m "feat: add GitHub Pages deployment workflow"
```

---

### Task 11: End-to-End Verification

**Step 1: Verify pipeline locally**

```bash
cd scripts
python fetch_new_videos.py          # Should find videos
python run_pipeline.py youtube      # Should download, transcribe, summarize
python build_index.py               # Should rebuild index
```

**Step 2: Verify frontend locally**

Open `site/index.html` in browser, confirm all features work with real data.

**Step 3: Push to GitHub and verify**

```bash
git push origin main
```

- Verify GitHub Pages deploys correctly
- Verify daily-summarize workflow appears in Actions tab
- Trigger workflow_dispatch manually to test

**Step 4: Final commit**

```bash
git commit -m "docs: finalize project setup"
```
