#!/usr/bin/env python3
"""Transcribe video/audio using OpenAI Whisper API, with YouTube subtitle fallback."""

import glob
import json
import os
import re
import sys
import subprocess
import tempfile
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
client = OpenAI()

MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB Whisper API limit
YT_COOKIES_FILE = os.environ.get('YT_COOKIES_FILE', '')


def extract_video_id(video_url):
    """Extract YouTube video ID from URL."""
    m = re.search(r'(?:v=|youtu\.be/|/shorts/)([\w-]{11})', video_url)
    return m.group(1) if m else None


def download_subtitles(video_id, tmp_dir):
    """Download YouTube subtitles (manual first, then auto-generated).

    Returns the path to the subtitle file, or None if unavailable.
    """
    cmd = [
        sys.executable, '-m', 'yt_dlp',
        '--write-sub', '--write-auto-sub',
        '--sub-lang', 'zh',
        '--sub-format', 'json3',
        '--skip-download',
        '-o', os.path.join(tmp_dir, '%(id)s.%(ext)s'),
    ]
    if YT_COOKIES_FILE:
        cmd += ['--cookies', YT_COOKIES_FILE]
    cmd.append(f'https://www.youtube.com/watch?v={video_id}')
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None

    # Prefer manual subtitle over auto-generated
    manual = glob.glob(os.path.join(tmp_dir, f'{video_id}.zh*.json3'))
    auto = [p for p in manual if '.zh' in os.path.basename(p)]
    # yt-dlp names: <id>.zh.json3 (manual) vs <id>.zh-orig.json3 or <id>.zh.json3
    # With --write-sub + --write-auto-sub, manual takes precedence in filename
    if manual:
        return manual[0]
    return None


def parse_json3_subtitles(json3_path):
    """Parse YouTube json3 subtitle file into Whisper-compatible format.

    Merges word-level events into sentence-level segments.
    Returns: {text, segments[{start, end, text}], duration}
    """
    with open(json3_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    events = data.get('events', [])

    # Collect raw text spans with timestamps
    raw_segments = []
    for event in events:
        segs = event.get('segs')
        if not segs:
            continue
        t_start_ms = event.get('tStartMs', 0)
        d_duration_ms = event.get('dDurationMs', 0)
        parts = []
        for seg in segs:
            utf8 = seg.get('utf8', '')
            if utf8 == '\n':
                continue
            parts.append(utf8)
        line = ''.join(parts).strip()
        if not line:
            continue
        raw_segments.append({
            'start': t_start_ms / 1000.0,
            'end': (t_start_ms + d_duration_ms) / 1000.0,
            'text': line,
        })

    if not raw_segments:
        return {'text': '', 'segments': [], 'duration': 0}

    # Merge short segments: combine until we hit punctuation or reach ~60 chars
    merged = []
    buf_start = raw_segments[0]['start']
    buf_end = raw_segments[0]['end']
    buf_text = ''
    SENTENCE_ENDERS = set('。！？!?.；;')

    for seg in raw_segments:
        if buf_text and (
            len(buf_text) >= 60
            or (buf_text and buf_text[-1] in SENTENCE_ENDERS)
        ):
            merged.append({
                'start': round(buf_start),
                'end': round(buf_end),
                'text': buf_text.strip(),
            })
            buf_start = seg['start']
            buf_text = ''

        buf_text += seg['text']
        buf_end = seg['end']

    if buf_text.strip():
        merged.append({
            'start': round(buf_start),
            'end': round(buf_end),
            'text': buf_text.strip(),
        })

    full_text = ''.join(seg['text'] for seg in merged)
    duration = round(raw_segments[-1]['end'])

    return {
        'text': full_text,
        'segments': merged,
        'duration': duration,
    }


def download_audio(video_url, output_dir):
    """Download audio from YouTube video using yt-dlp."""
    output_path = os.path.join(output_dir, '%(id)s.%(ext)s')
    cmd = [
        sys.executable, '-m', 'yt_dlp',
        '-x',
        '--audio-format', 'mp3',
        '--audio-quality', '5',
        '-o', output_path,
    ]
    if YT_COOKIES_FILE:
        cmd += ['--cookies', YT_COOKIES_FILE]
    cmd.append(video_url)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {result.stderr}")

    for f in os.listdir(output_dir):
        if f.endswith('.mp3'):
            return os.path.join(output_dir, f)
    raise FileNotFoundError("No audio file found after download")


def compress_audio(input_path, output_dir):
    """Extract and compress audio to MP3 under 25MB using ffmpeg.

    Automatically lowers bitrate if the first pass is still over the limit.
    """
    output_path = os.path.join(output_dir, 'compressed.mp3')
    input_size_mb = os.path.getsize(input_path) / 1024 / 1024

    for bitrate in ('48k', '32k', '24k'):
        cmd = [
            'ffmpeg', '-i', input_path,
            '-vn',                    # No video
            '-ac', '1',               # Mono
            '-ar', '16000',           # 16kHz sample rate (good enough for speech)
            '-b:a', bitrate,
            '-y',                     # Overwrite
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {result.stderr}")

        final_size = os.path.getsize(output_path)
        print(f"  Compressed ({bitrate}): {input_size_mb:.1f}MB -> {final_size / 1024 / 1024:.1f}MB", file=sys.stderr)

        if final_size <= MAX_FILE_SIZE:
            return output_path

    # If still over limit after lowest bitrate, return anyway and let API error
    return output_path


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
        start = seg.start if hasattr(seg, 'start') else seg['start']
        end = seg.end if hasattr(seg, 'end') else seg['end']
        text = seg.text if hasattr(seg, 'text') else seg['text']
        segments.append({
            'start': round(start),
            'end': round(end),
            'text': text.strip()
        })

    return {
        'text': response.text,
        'segments': segments,
        'duration': round(response.duration) if hasattr(response, 'duration') else None
    }


def transcribe_video(video_url):
    """Download and transcribe a YouTube video.

    Tries YouTube subtitles first (free), falls back to Whisper API.
    """
    video_id = extract_video_id(video_url)

    with tempfile.TemporaryDirectory() as tmp_dir:
        # Try YouTube subtitles first
        if video_id:
            print(f"Checking YouTube subtitles for {video_id}...", file=sys.stderr)
            sub_path = download_subtitles(video_id, tmp_dir)
            if sub_path:
                print(f"  Found subtitles: {os.path.basename(sub_path)}", file=sys.stderr)
                return parse_json3_subtitles(sub_path)
            print("  No subtitles found, falling back to Whisper.", file=sys.stderr)

        # Fallback: download audio → Whisper
        print(f"Downloading audio from {video_url}...", file=sys.stderr)
        audio_path = download_audio(video_url, tmp_dir)

        # Compress if over size limit
        if os.path.getsize(audio_path) > MAX_FILE_SIZE:
            print(f"File too large, compressing...", file=sys.stderr)
            audio_path = compress_audio(audio_path, tmp_dir)

        print(f"Transcribing with Whisper...", file=sys.stderr)
        return transcribe_audio(audio_path)


def transcribe_file(file_path):
    """Transcribe a local audio/video file. Auto-compresses if needed."""
    print(f"Transcribing {file_path}...", file=sys.stderr)

    file_size = os.path.getsize(file_path)
    ext = os.path.splitext(file_path)[1].lower()

    # Always extract audio from video files, or compress if over limit
    if ext in ('.mp4', '.webm', '.mkv', '.avi') or file_size > MAX_FILE_SIZE:
        with tempfile.TemporaryDirectory() as tmp_dir:
            print(f"  Extracting & compressing audio ({file_size / 1024 / 1024:.1f}MB)...", file=sys.stderr)
            compressed = compress_audio(file_path, tmp_dir)
            return transcribe_audio(compressed)

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
