#!/usr/bin/env python3
"""Run the full pipeline: fetch new videos -> transcribe -> summarize -> build index."""

import json
import os
import sys
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

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
            err_msg = str(e)
            if 'Sign in' in err_msg or 'members-only' in err_msg.lower():
                print(f"Skipping (paid/members-only): {video['title']}", file=sys.stderr)
            else:
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
