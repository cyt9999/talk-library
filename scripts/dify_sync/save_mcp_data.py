#!/usr/bin/env python3
"""Save MCP API response data as JSON files for processing.

Usage: pipe JSON data via stdin or provide file paths as arguments.
This is a helper script - the actual MCP calls are made via Claude Code.
"""

import json
import os
import sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
MCP_RAW_DIR = os.path.join(ROOT_DIR, 'data', 'mcp', 'raw')


def save_result(result_json, output_dir=MCP_RAW_DIR):
    """Save a single MCP API result as a JSON file with an appropriate name."""
    os.makedirs(output_dir, exist_ok=True)

    if isinstance(result_json, str):
        data = json.loads(result_json)
    else:
        data = result_json

    source = data.get("source", {})
    source_type = source.get("type", "unknown")
    board_id = source.get("boardId", "")
    author_id = source.get("authorId", "")
    pricing = source.get("pricingModel", "")

    # Build filename
    parts = [source_type.lower()]
    if board_id:
        parts.append(f"board-{board_id}")
    if author_id:
        parts.append(f"author-{author_id}")
    if pricing:
        parts.append(pricing)

    filename = "-".join(parts) + ".json"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Saved: {filepath} ({data.get('total', 0)} items)", file=sys.stderr)
    return filepath


if __name__ == "__main__":
    # Read from stdin
    data = json.load(sys.stdin)
    if isinstance(data, dict) and "result" in data:
        save_result(data["result"])
    else:
        save_result(data)
