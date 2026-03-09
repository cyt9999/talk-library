#!/usr/bin/env python3
"""Fetch tweets from @TJ_Research via X API v2."""

import json
import os
import sys

import requests

from config import X_BEARER_TOKEN, X_TARGET_USERNAME, X_TARGET_USER_ID, TWEETS_DIR, TWEETS_FILE

TWITTER_API_BASE = "https://api.twitter.com/2"

# Cache file for user ID to avoid extra API calls
USER_ID_CACHE = os.path.join(TWEETS_DIR, ".user_id_cache.json")


def get_headers():
    return {"Authorization": f"Bearer {X_BEARER_TOKEN}"}


def get_user_id(username):
    """Look up X user ID from username. Uses hardcoded ID or cache to avoid API calls."""
    # Use hardcoded ID for known username (saves an API call)
    if username == X_TARGET_USERNAME and X_TARGET_USER_ID:
        print(f"Using known user ID for @{username}", file=sys.stderr)
        return X_TARGET_USER_ID

    # Check cache
    if os.path.exists(USER_ID_CACHE):
        with open(USER_ID_CACHE, 'r') as f:
            cache = json.load(f)
        if cache.get("username") == username:
            print(f"Using cached user ID for @{username}", file=sys.stderr)
            return cache["id"]

    url = f"{TWITTER_API_BASE}/users/by/username/{username}"
    resp = requests.get(url, headers=get_headers())
    if resp.status_code in (402, 429):
        print(f"Warning: X API limit ({resp.status_code}) on user lookup.", file=sys.stderr)
        print("Error: Cannot resolve user ID and no cache available.", file=sys.stderr)
        sys.exit(1)
    resp.raise_for_status()
    data = resp.json()
    if "data" not in data:
        print(f"Error: User @{username} not found. Response: {data}", file=sys.stderr)
        sys.exit(1)

    user_id = data["data"]["id"]

    # Save to cache
    os.makedirs(TWEETS_DIR, exist_ok=True)
    with open(USER_ID_CACHE, 'w') as f:
        json.dump({"username": username, "id": user_id}, f)

    return user_id


def load_existing_tweets():
    """Load previously saved tweets, or return empty list."""
    if os.path.exists(TWEETS_FILE):
        with open(TWEETS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def fetch_tweets(user_id, since_id=None):
    """Fetch tweets from user, handling pagination. Uses since_id for incremental fetches."""
    url = f"{TWITTER_API_BASE}/users/{user_id}/tweets"
    params = {
        "max_results": 100,
        "tweet.fields": "created_at,text,public_metrics",
    }
    if since_id:
        params["since_id"] = since_id

    all_tweets = []
    while True:
        resp = requests.get(url, headers=get_headers(), params=params)
        if resp.status_code in (402, 429):
            print(f"Warning: Hit X API limit ({resp.status_code}). "
                  f"Saving {len(all_tweets)} tweets fetched so far.", file=sys.stderr)
            break
        resp.raise_for_status()
        data = resp.json()

        tweets = data.get("data", [])
        if not tweets:
            break

        for t in tweets:
            all_tweets.append({
                "id": t["id"],
                "text": t["text"],
                "created_at": t["created_at"],
                "metrics": t.get("public_metrics", {})
            })

        next_token = data.get("meta", {}).get("next_token")
        if not next_token:
            break
        params["pagination_token"] = next_token

    return all_tweets


def save_tweets(tweets):
    """Save tweets to JSON file."""
    os.makedirs(TWEETS_DIR, exist_ok=True)
    with open(TWEETS_FILE, 'w', encoding='utf-8') as f:
        json.dump(tweets, f, ensure_ascii=False, indent=2)


def main():
    if not X_BEARER_TOKEN:
        print("Error: X bearer token not set. Set X_BEARER_TOKEN in .env",
              file=sys.stderr)
        sys.exit(1)

    print(f"Fetching tweets from @{X_TARGET_USERNAME}...", file=sys.stderr)
    user_id = get_user_id(X_TARGET_USERNAME)

    existing = load_existing_tweets()
    existing_ids = {t["id"] for t in existing}

    # Use the highest tweet ID as since_id for incremental fetches
    since_id = max((t["id"] for t in existing), default=None) if existing else None

    new_tweets = fetch_tweets(user_id, since_id=since_id)
    new_tweets = [t for t in new_tweets if t["id"] not in existing_ids]

    all_tweets = new_tweets + existing
    all_tweets.sort(key=lambda t: t["created_at"], reverse=True)

    save_tweets(all_tweets)
    print(f"Fetched {len(new_tweets)} new tweets from @{X_TARGET_USERNAME} "
          f"(total: {len(all_tweets)})")


if __name__ == "__main__":
    main()
