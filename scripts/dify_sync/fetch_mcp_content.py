#!/usr/bin/env python3
"""Fetch content from authorcontentsource MCP API and save as JSON.

This script is designed to be called from Claude Code or CI with MCP access.
For now, it reads pre-fetched JSON files from data/mcp/raw/ and converts them.
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
MCP_DIR = os.path.join(ROOT_DIR, 'data', 'mcp')
MCP_RAW_DIR = os.path.join(MCP_DIR, 'raw')

# Board name mapping
BOARD_NAMES = {
    "10918": "社團大廳",
    "10919": "持倉/總經",
    "10921": "VIP會員專屬",
    "12784": "VIP聊天室",
}

AUTHOR_ID = "17427140"


def ts_to_date(ts_ms):
    """Convert millisecond timestamp to YYYY-MM-DD string (Asia/Taipei)."""
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone(timedelta(hours=8)))
    return dt.strftime("%Y-%m-%d")


def ts_to_datetime(ts_ms):
    """Convert millisecond timestamp to readable datetime string."""
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone(timedelta(hours=8)))
    return dt.strftime("%Y-%m-%d %H:%M")


def group_articles_to_markdown(articles, board_id):
    """Convert group articles to Markdown, grouped by date."""
    board_name = BOARD_NAMES.get(board_id, board_id)

    # Group by date
    by_date = {}
    for art in articles:
        date = ts_to_date(art["createTime"])
        by_date.setdefault(date, []).append(art)

    results = []
    for date, arts in sorted(by_date.items()):
        lines = [
            "---",
            "source: group_article",
            f"board_id: {board_id}",
            f"board_name: {board_name}",
            f"date: {date}",
            f"article_count: {len(arts)}",
            f"fetched_at: {datetime.now().isoformat()}",
            "---",
            "",
            f"# {board_name} - 社團文章 ({date})",
            "",
        ]
        for art in sorted(arts, key=lambda x: x["createTime"]):
            title = art.get("contentTitle", "").strip() or "(無標題)"
            text = art.get("contentText", "").strip()
            creator = art.get("creatorName", "未知")
            time_str = ts_to_datetime(art["createTime"])

            lines.append(f"## {title}")
            lines.append(f"- 發文者: {creator}")
            lines.append(f"- 時間: {time_str}")
            if text:
                lines.append("")
                lines.append(text)
            lines.append("")
            lines.append("---")
            lines.append("")

        md_filename = f"club-{board_id}-{date}.md"
        results.append((md_filename, "\n".join(lines)))

    return results


def chatroom_articles_to_markdown(articles, board_id):
    """Convert chatroom articles to Markdown, grouped by date."""
    board_name = BOARD_NAMES.get(board_id, board_id)

    by_date = {}
    for art in articles:
        date = ts_to_date(art["createTime"])
        by_date.setdefault(date, []).append(art)

    results = []
    for date, arts in sorted(by_date.items()):
        lines = [
            "---",
            "source: chatroom",
            f"board_id: {board_id}",
            f"board_name: {board_name}",
            f"date: {date}",
            f"article_count: {len(arts)}",
            f"fetched_at: {datetime.now().isoformat()}",
            "---",
            "",
            f"# {board_name} - 聊天室 ({date})",
            "",
        ]
        for art in sorted(arts, key=lambda x: x["createTime"]):
            text = art.get("contentText", "").strip()
            creator = art.get("creatorName", "未知")
            time_str = ts_to_datetime(art["createTime"])

            lines.append(f"### {creator} ({time_str})")
            if text:
                lines.append("")
                lines.append(text)
            lines.append("")
            lines.append("---")
            lines.append("")

        md_filename = f"chatroom-{board_id}-{date}.md"
        results.append((md_filename, "\n".join(lines)))

    return results


def convert_all_mcp_data():
    """Read all MCP JSON data and convert to Markdown files."""
    all_files = []

    for fname in sorted(os.listdir(MCP_RAW_DIR)):
        if not fname.endswith('.json'):
            continue
        filepath = os.path.join(MCP_RAW_DIR, fname)
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        source_type = data.get("source", {}).get("type", "")
        board_id = data.get("source", {}).get("boardId", "")

        if source_type == "GroupArticle":
            articles = data.get("articles", [])
            if articles:
                files = group_articles_to_markdown(articles, board_id)
                all_files.extend(files)
                print(f"  {fname}: {len(articles)} articles → {len(files)} MD files",
                      file=sys.stderr)

        elif source_type == "ChatroomArticle":
            articles = data.get("chatroomArticles", [])
            if articles:
                files = chatroom_articles_to_markdown(articles, board_id)
                all_files.extend(files)
                print(f"  {fname}: {len(articles)} articles → {len(files)} MD files",
                      file=sys.stderr)

        elif source_type == "InvestmentNote":
            notes = data.get("investmentNotes", [])
            if notes:
                print(f"  {fname}: {len(notes)} notes", file=sys.stderr)
                # TODO: implement when data is available

        elif source_type == "MediaProduct":
            products = data.get("mediaProducts", [])
            if products:
                print(f"  {fname}: {len(products)} products", file=sys.stderr)
                # TODO: implement when data is available

    return all_files


if __name__ == "__main__":
    os.makedirs(MCP_RAW_DIR, exist_ok=True)
    files = convert_all_mcp_data()
    print(f"\nTotal: {len(files)} Markdown files generated", file=sys.stderr)

    # Optionally write to disk for inspection
    if "--write" in sys.argv:
        out_dir = os.path.join(MCP_DIR, "markdown")
        os.makedirs(out_dir, exist_ok=True)
        for name, content in files:
            with open(os.path.join(out_dir, name), 'w', encoding='utf-8') as f:
                f.write(content)
        print(f"Written to {out_dir}", file=sys.stderr)
