#!/usr/bin/env python3
"""Summarize transcript using OpenAI GPT API. Extract tickers, sentiment, timestamps."""

import json
import os
import sys
from datetime import datetime, timezone
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
client = OpenAI()

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
    """Send transcript to OpenAI GPT for summarization."""
    timestamped_text = ""
    for seg in segments:
        minutes = seg['start'] // 60
        seconds = seg['start'] % 60
        timestamped_text += f"[{minutes:02d}:{seconds:02d}] {seg['text']}\n"

    response = client.chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "You are a professional US stock investment analyst. Always respond with valid JSON."},
            {"role": "user", "content": SUMMARY_PROMPT.format(transcript=timestamped_text)}
        ]
    )

    result_text = response.choices[0].message.content.strip()
    return json.loads(result_text)


def convert_to_traditional(simplified_data):
    """Convert simplified Chinese summary to traditional Chinese."""
    json_str = json.dumps(simplified_data, ensure_ascii=False, indent=2)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "You convert Simplified Chinese to Traditional Chinese. Always respond with valid JSON."},
            {"role": "user", "content": CONVERT_PROMPT.format(json_content=json_str)}
        ]
    )

    result_text = response.choices[0].message.content.strip()
    return json.loads(result_text)


def create_summary(video_info, transcript):
    """Create full summary JSON from video info and transcript."""
    print(f"Summarizing: {video_info['title']}...", file=sys.stderr)

    zh_hans_result = summarize_transcript(transcript['text'], transcript['segments'])

    print("Converting to Traditional Chinese...", file=sys.stderr)
    zh_hant_data = {
        'keyPoints': zh_hans_result['keyPoints'],
        'paragraph': zh_hans_result['paragraph'],
        'tags': zh_hans_result['tags']
    }
    zh_hant_result = convert_to_traditional(zh_hant_data)

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
    if not summary['publishedAt']:
        summary['publishedAt'] = datetime.now().strftime('%Y-%m-%d')
    date_str = summary['publishedAt'][:10]
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
