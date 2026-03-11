"""Centralized config loading from .env for the dify_sync package."""

import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'), override=False)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
VECTOR_STORE_ID = os.getenv("VECTOR_STORE_ID", "")
X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN") or os.getenv("XApi:BearerToken", "")
X_TARGET_USERNAME = "TJ_Research"
X_TARGET_USER_ID = "1620475218627121153"

# Paths
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
SUMMARIES_DIR = os.path.join(ROOT_DIR, 'data', 'summaries')
TWEETS_DIR = os.path.join(ROOT_DIR, 'data', 'tweets')
TWEETS_FILE = os.path.join(TWEETS_DIR, 'tweets.json')
SHEETS_DIR = os.path.join(ROOT_DIR, 'data', 'sheets')
DOCS_DIR = os.path.join(ROOT_DIR, 'data', 'docs')
MCP_RAW_DIR = os.path.join(ROOT_DIR, 'data', 'mcp', 'raw')

# Google Sheets
GOOGLE_SERVICE_ACCOUNT_KEY = os.getenv("GOOGLE_SERVICE_ACCOUNT_KEY", "")

GOOGLE_SHEETS = [
    {"id": os.getenv("SHEET_ID_MACRO", ""), "slug": "macro-announcements", "name": "投資talk君-總經公告"},
    {"id": os.getenv("SHEET_ID_POSITIONS", ""), "slug": "positions-ytd", "name": "投資Talk君-持倉績效 ytd"},
    {"id": os.getenv("SHEET_ID_DATASOURCES", ""), "slug": "data-sources", "name": "投資talk君-資料來源"},
    {"id": os.getenv("SHEET_ID_BETA", ""), "slug": "portfolio-beta", "name": "投資talk君-持倉Beta"},
    {"id": os.getenv("SHEET_ID_COMMUNITY", ""), "slug": "community-posts", "name": "爬蟲-投資talk君2025文章"},
]
