#!/usr/bin/env python3
"""Transcribe video/audio using OpenAI Whisper API."""

import json
import os
import sys
import subprocess
import tempfile
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
client = OpenAI()

MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB Whisper API limit


def download_audio(video_url, output_dir):
    """Download audio from YouTube video using yt-dlp."""
    output_path = os.path.join(output_dir, '%(id)s.%(ext)s')
    cmd = [
        sys.executable, '-m', 'yt_dlp',
        '-x',
        '--audio-format', 'mp3',
        '--audio-quality', '5',
        '-o', output_path,
        video_url
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {result.stderr}")

    for f in os.listdir(output_dir):
        if f.endswith('.mp3'):
            return os.path.join(output_dir, f)
    raise FileNotFoundError("No audio file found after download")


def compress_audio(input_path, output_dir):
    """Extract and compress audio to MP3 under 25MB using ffmpeg."""
    output_path = os.path.join(output_dir, 'compressed.mp3')
    cmd = [
        'ffmpeg', '-i', input_path,
        '-vn',                    # No video
        '-ac', '1',               # Mono
        '-ar', '16000',           # 16kHz sample rate (good enough for speech)
        '-b:a', '48k',            # Low bitrate for small file size
        '-y',                     # Overwrite
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr}")

    final_size = os.path.getsize(output_path)
    print(f"  Compressed: {os.path.getsize(input_path) / 1024 / 1024:.1f}MB -> {final_size / 1024 / 1024:.1f}MB", file=sys.stderr)
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
    """Download and transcribe a YouTube video."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        print(f"Downloading audio from {video_url}...", file=sys.stderr)
        audio_path = download_audio(video_url, tmp_dir)

        # Compress if over size limit
        if os.path.getsize(audio_path) > MAX_FILE_SIZE:
            print(f"File too large, compressing...", file=sys.stderr)
            audio_path = compress_audio(audio_path, tmp_dir)

        print(f"Transcribing...", file=sys.stderr)
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
