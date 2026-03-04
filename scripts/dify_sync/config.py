"""Centralized config loading from .env for the dify_sync package."""

import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
VECTOR_STORE_ID = os.getenv("VECTOR_STORE_ID", "")
X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN") or os.getenv("XApi:BearerToken", "")
X_TARGET_USERNAME = "TJ_Research"

# Paths
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
SUMMARIES_DIR = os.path.join(ROOT_DIR, 'data', 'summaries')
TWEETS_DIR = os.path.join(ROOT_DIR, 'data', 'tweets')
TWEETS_FILE = os.path.join(TWEETS_DIR, 'tweets.json')
