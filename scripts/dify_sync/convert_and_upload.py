#!/usr/bin/env python3
"""Convert JSON summaries + tweets to Markdown and upload to OpenAI vector store."""

import json
import os
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timedelta

from openai import OpenAI

from config import VECTOR_STORE_ID, SUMMARIES_DIR, TWEETS_FILE

client = OpenAI()

VECTOR_STORE_NAME = "投資Talk君-知識庫"

SENTIMENT_MAP = {"bullish": "看多", "bearish": "看空", "neutral": "中性"}


def summary_to_markdown(data):
    """Convert a summary JSON to Markdown using zh-Hant version."""
    hant = data["summary"].get("zh-Hant", data["summary"].get("zh-Hans", {}))

    title = data.get("title", "無標題")
    date = data.get("publishedAt", "未知日期")
    tags = hant.get("tags", [])
    paragraph = hant.get("paragraph", "")
    key_points = hant.get("keyPoints", [])
    tickers = data.get("tickers", [])

    lines = [f"# {title}"]
    lines.append(f"- 日期：{date}")
    lines.append("- 來源：YouTube")
    if tags:
        lines.append(f"- 標籤：{', '.join(tags)}")
    if tickers:
        ticker_strs = []
        for t in tickers:
            s = SENTIMENT_MAP.get(t.get("sentiment", "neutral"), t.get("sentiment", ""))
            ticker_strs.append(f"{t['symbol']} ({s})")
        lines.append(f"- 提及股票：{', '.join(ticker_strs)}")
    lines.append("")

    lines.append("## 摘要")
    lines.append(paragraph)

    if key_points:
        lines.append("")
        lines.append("## 重點")
        for kp in key_points:
            ts = kp.get("timestamp", 0)
            minutes = ts // 60
            seconds = ts % 60
            lines.append(f"- [{minutes}:{seconds:02d}] {kp['text']}")

    if tickers:
        lines.append("")
        lines.append("## 股票分析")
        for t in tickers:
            sentiment_zh = SENTIMENT_MAP.get(t.get("sentiment", "neutral"), t.get("sentiment", ""))
            lines.append(f"### {t['symbol']} ({t.get('name', '')}) — {sentiment_zh}")
            for m in t.get("mentions", []):
                lines.append(m.get("context", ""))

    return "\n".join(lines)


def tweets_to_markdown_by_week(tweets):
    """Group tweets by ISO week and return list of (filename, markdown) tuples."""
    weeks = defaultdict(list)
    for t in tweets:
        dt = datetime.fromisoformat(t["created_at"].replace("Z", "+00:00"))
        iso_year, iso_week, _ = dt.isocalendar()
        weeks[(iso_year, iso_week)].append((dt, t))

    results = []
    for (year, week_num), tweet_list in sorted(weeks.items()):
        tweet_list.sort(key=lambda x: x[0], reverse=True)

        first_day = datetime.fromisocalendar(year, week_num, 1)
        last_day = first_day + timedelta(days=6)

        lines = [
            f"# X 平台短評 — {year}年第{week_num}週 "
            f"({first_day.strftime('%m/%d')}-{last_day.strftime('%m/%d')})"
        ]
        lines.append("- 來源：X (@TJ_Research)")
        lines.append("")

        current_date = None
        for dt, tweet in tweet_list:
            date_str = dt.strftime("%Y-%m-%d")
            if date_str != current_date:
                current_date = date_str
                lines.append(f"## {date_str}")
                lines.append("")
            lines.append(tweet["text"])
            lines.append("")

        filename = f"tweets-{year}-W{week_num:02d}.md"
        results.append((filename, "\n".join(lines)))

    return results


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


def upload_markdown_files(vector_store, md_files):
    """Upload list of (filename, content) tuples to vector store."""
    uploaded = 0
    for filename, content in md_files:
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
                vector_store_id=vector_store.id,
                file_id=file_obj.id
            )
            uploaded += 1
            print(f"  Uploaded: {filename}", file=sys.stderr)
        finally:
            os.unlink(tmp.name)
    return uploaded


def main():
    tweets_only = "--tweets-only" in sys.argv

    vector_store = get_or_create_vector_store()
    md_files = []

    # Convert YouTube summaries
    if not tweets_only:
        if os.path.isdir(SUMMARIES_DIR):
            for fname in sorted(os.listdir(SUMMARIES_DIR)):
                if not fname.endswith('.json'):
                    continue
                filepath = os.path.join(SUMMARIES_DIR, fname)
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                md = summary_to_markdown(data)
                md_filename = fname.replace('.json', '.md')
                md_files.append((md_filename, md))
            print(f"Converted {len(md_files)} YouTube summaries to Markdown", file=sys.stderr)
        else:
            print(f"Warning: Summaries directory not found: {SUMMARIES_DIR}",
                  file=sys.stderr)

    # Convert tweets
    if os.path.exists(TWEETS_FILE):
        with open(TWEETS_FILE, 'r', encoding='utf-8') as f:
            tweets = json.load(f)
        if tweets:
            tweet_mds = tweets_to_markdown_by_week(tweets)
            md_files.extend(tweet_mds)
            print(f"Converted tweets into {len(tweet_mds)} weekly Markdown files",
                  file=sys.stderr)
    elif tweets_only:
        print("No tweets file found. Run fetch_tweets.py first.", file=sys.stderr)
        sys.exit(1)
    else:
        print("No tweets file found, skipping tweets.", file=sys.stderr)

    if not md_files:
        print("No files to upload.", file=sys.stderr)
        sys.exit(1)

    count = upload_markdown_files(vector_store, md_files)
    print(f"\nUploaded {count} files to vector store {vector_store.id}")


if __name__ == "__main__":
    main()
