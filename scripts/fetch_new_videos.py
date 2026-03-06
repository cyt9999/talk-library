#!/usr/bin/env python3
"""Fetch new videos from YouTube channels that haven't been summarized yet."""

import json
import os
import sys
import subprocess

CHANNELS_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'channels.json')
SUMMARIES_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'summaries')
MAX_VIDEOS = 15  # How many recent videos to check per channel


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


def fetch_channel_videos(channel_url, limit):
    """Use yt-dlp to list recent videos from a channel."""
    cmd = [
        sys.executable, '-m', 'yt_dlp',
        '--flat-playlist',
        '--dump-json',
        '--playlist-end', str(limit),
        channel_url + '/videos'
    ]
    result = subprocess.run(cmd, capture_output=True, encoding='utf-8')
    if result.returncode != 0:
        print(f"Warning: yt-dlp failed for {channel_url}: {result.stderr}", file=sys.stderr)
        return []

    videos = []
    for line in result.stdout.strip().split('\n'):
        if not line:
            continue
        try:
            data = json.loads(line)
            videos.append(data)
        except json.JSONDecodeError:
            continue
    return videos


def fetch_video_date(video_id):
    """Fetch actual upload date for a single video via yt-dlp."""
    cmd = [
        sys.executable, '-m', 'yt_dlp',
        '--print', '%(upload_date)s',
        '--no-download',
        f'https://www.youtube.com/watch?v={video_id}'
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, encoding='utf-8', timeout=30)
        raw = result.stdout.strip()
        if result.returncode == 0 and raw and raw != 'NA' and len(raw) == 8:
            return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    except subprocess.TimeoutExpired:
        print(f"Warning: timeout fetching date for {video_id}", file=sys.stderr)
    return ''


def fetch_new_videos():
    """Fetch recent videos from all channels and return ones without summaries."""
    with open(CHANNELS_PATH, 'r', encoding='utf-8') as f:
        channels = json.load(f)

    existing_ids = get_existing_video_ids()
    new_videos = []

    for channel in channels:
        channel_url = channel['rssUrl']  # Now used as channel URL for yt-dlp
        print(f"Fetching videos for {channel['name']}: {channel_url}", file=sys.stderr)

        yt_videos = fetch_channel_videos(channel_url, MAX_VIDEOS)

        for data in yt_videos:
            video_id = data.get('id', '')
            if video_id and video_id not in existing_ids:
                upload_date = data.get('upload_date') or data.get('release_date') or ''
                if upload_date and len(upload_date) == 8:
                    upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}"

                # --flat-playlist doesn't return dates; fetch individually
                if not upload_date:
                    print(f"Fetching date for {video_id}...", file=sys.stderr)
                    upload_date = fetch_video_date(video_id)
                    if not upload_date:
                        print(f"Warning: could not get upload_date for {video_id} ({data.get('title', '')})", file=sys.stderr)

                new_videos.append({
                    'videoId': video_id,
                    'title': data.get('title', ''),
                    'publishedAt': upload_date,
                    'channelName': channel['name'],
                    'channelId': channel['id'],
                    'duration': data.get('duration', 0),
                    'videoUrl': f"https://www.youtube.com/watch?v={video_id}",
                    'thumbnailUrl': f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
                })

    return new_videos


if __name__ == '__main__':
    videos = fetch_new_videos()
    # Output with utf-8 encoding
    output = json.dumps(videos, ensure_ascii=False, indent=2)
    sys.stdout.buffer.write(output.encode('utf-8'))
    sys.stdout.buffer.write(b'\n')
    print(f"\nFound {len(videos)} new video(s)", file=sys.stderr)
