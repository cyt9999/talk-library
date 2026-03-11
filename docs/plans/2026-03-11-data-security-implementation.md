# Data Security Redesign — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove all sensitive data from the public repo; CI uploads directly to Vector Store without committing; frontend fetches video data from Render API instead of static files.

**Architecture:** GitHub Pages serves UI only (HTML/CSS/JS). Render API serves both chat (`/api/ask`) and video data (`/api/videos`, `/api/summary/:id`). CI fetches from all sources, converts to Markdown, uploads to Vector Store, and exits — no git commit of data. `data/index.json` stays in repo (public YouTube metadata only).

**Tech Stack:** Python 3.12, OpenAI API, GitHub Actions, Render (Docker), vanilla JS frontend

**Design Doc:** `docs/plans/2026-03-11-data-security-redesign.md`

---

### Task 1: Add `/api/videos` and `/api/summary/:id` endpoints to Render API

The frontend currently loads video data from static files (`data/index.json` and `data/summaries/*.json`). We need API endpoints so the frontend can fetch this data from Render instead.

**Approach:** `data/index.json` stays in repo (public YouTube metadata, not sensitive). The Render API reads it at startup. For individual summaries, we read from the Vector Store (summaries are already uploaded there as Markdown).

However, the Vector Store is optimized for semantic search, not direct file retrieval. A simpler approach: the daily CI generates `index.json` and uploads it as a file to OpenAI Files, and the Render API downloads it on startup. But the simplest: keep `index.json` in the repo since it's public YouTube data.

For summaries: the frontend summary page needs full JSON (keyPoints, tickers, paragraph). These are NOT in Vector Store in JSON format — they're converted to Markdown. So we need to keep serving them somehow.

**Decision:** Keep `data/index.json` in repo. For summaries, add a new CI step that uploads a combined `summaries-bundle.json` to OpenAI Files, and the Render API loads it on startup.

Actually — simpler: the Render Dockerfile can bake `data/index.json` into the image. But `data/` won't exist in repo anymore...

**Simplest viable approach:**
- `data/index.json` stays in repo (not sensitive — just YouTube titles/dates/IDs)
- Summary detail pages: the frontend calls `/api/summary?id=X&date=Y` → Render API uses `file_search` to retrieve the relevant video summary from Vector Store and returns it

**Files:**
- Modify: `scripts/dify_sync/web_demo.py` (add GET handlers for `/api/videos` and `/api/summary`)
- Modify: `site/js/app.js` (change `fetchIndex` and `fetchSummary` to call API)
- Keep: `data/index.json` (public metadata, stays in repo)

**Step 1: Add `/api/videos` endpoint to `web_demo.py`**

In `web_demo.py`, the `do_GET` method currently only handles `/health` and static files. Add a `/api/videos` handler that returns `index.json`.

Since `index.json` won't be on the Render filesystem (it's in the repo, not in the Docker context), we have two options:
- Bake it into Docker image by copying from repo
- Fetch it from GitHub raw URL at startup

Best: copy `data/index.json` into the Docker build context.

Add to `scripts/dify_sync/Dockerfile`:
```dockerfile
COPY ../../data/index.json /app/data/index.json
```

Wait — Docker context is `scripts/dify_sync/`. We can't COPY outside the context. Change the Docker context in `render.yaml` to repo root, or move index.json into the build context.

**Revised approach:** Change `render.yaml` Docker context to repo root. Update Dockerfile paths accordingly.

```yaml
# render.yaml
services:
  - type: web
    name: talk-ai-api
    runtime: docker
    dockerfilePath: scripts/dify_sync/Dockerfile
    dockerContext: .          # Changed from scripts/dify_sync
    region: singapore
    plan: free
```

```dockerfile
# Dockerfile — updated paths
FROM python:3.12-slim
WORKDIR /app
COPY scripts/dify_sync/requirements-api.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY scripts/dify_sync/*.py ./
COPY data/index.json ./data/index.json
EXPOSE 8080
CMD ["python", "web_demo.py"]
```

Then in `web_demo.py`:
```python
def do_GET(self):
    if self.path == "/health":
        # ... existing health check
    elif self.path == "/api/videos":
        self._serve_json_file("/app/data/index.json")
    elif self.path.startswith("/api/summary"):
        self._serve_summary()
    else:
        # ... existing static file handling
```

**Step 2: Add `/api/summary` endpoint**

For individual video summaries, the full JSON data won't be on disk. Use OpenAI file_search to retrieve the summary content from Vector Store.

```python
def _serve_summary(self):
    """Serve a video summary by querying Vector Store."""
    from urllib.parse import urlparse, parse_qs
    params = parse_qs(urlparse(self.path).query)
    video_id = params.get("id", [None])[0]
    date = params.get("date", [None])[0]

    if not video_id:
        self.send_response(400)
        self.send_header("Content-Type", "application/json")
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(b'{"error":"missing id param"}')
        return

    # Search Vector Store for this video's summary
    query = f"video {video_id} {date or ''}"
    response = client.responses.create(
        model="gpt-4o-mini",
        tools=[{"type": "file_search", "vector_store_ids": [VECTOR_STORE_ID]}],
        input=f"Return the COMPLETE content of the video summary for video ID {video_id} dated {date}. Return ALL key points, tickers, and the full paragraph summary. Do not summarize or shorten."
    )

    # Extract answer
    answer = ""
    for item in response.output:
        if item.type == "message":
            for block in item.content:
                if block.type == "output_text":
                    answer = block.text

    self.send_response(200)
    self.send_header("Content-Type", "application/json; charset=utf-8")
    self._send_cors_headers()
    self.end_headers()
    self.wfile.write(json.dumps({
        "id": video_id,
        "date": date,
        "summary": answer
    }, ensure_ascii=False).encode("utf-8"))
```

**Step 3: Update `site/js/app.js` to fetch from API**

Change `fetchIndex()` and `fetchSummary()` to use the Render API:

```javascript
// Replace DATA_BASE usage for index and summaries
var API_BASE = (function () {
    var host = window.location.hostname;
    if (host === 'localhost' || host === '127.0.0.1') {
        return 'http://localhost:8080';
    }
    var meta = document.querySelector('meta[name="chat-api-url"]');
    if (meta && meta.content) {
        // Derive base URL from chat API URL (strip /api/ask)
        return meta.content.replace(/\/api\/ask$/, '');
    }
    return 'http://localhost:8080';
})();

function fetchIndex() {
    return fetch(API_BASE + '/api/videos')
        .then(function (res) {
            if (!res.ok) throw new Error('HTTP ' + res.status);
            return res.json();
        });
}

function fetchSummary(id, publishedAt) {
    var params = 'id=' + encodeURIComponent(id);
    if (publishedAt) params += '&date=' + encodeURIComponent(publishedAt);
    return fetch(API_BASE + '/api/summary?' + params)
        .then(function (res) {
            if (!res.ok) throw new Error('HTTP ' + res.status);
            return res.json();
        });
}
```

**Step 4: Add `api-base-url` meta tag to all HTML pages**

Add to `index.html`, `summary.html`, `ticker.html`, `bookmarks.html`:
```html
<meta name="api-base-url" content="https://talk-library.onrender.com">
```

Update `app.js` to read from this meta tag instead of deriving from chat-api-url.

**Step 5: Commit**

```bash
git add scripts/dify_sync/web_demo.py scripts/dify_sync/Dockerfile render.yaml site/js/app.js site/index.html site/summary.html site/ticker.html site/bookmarks.html
git commit -m "feat: add /api/videos and /api/summary endpoints, frontend fetches from API"
```

---

### Task 2: Update CI workflows to stop committing data

**Files:**
- Modify: `.github/workflows/daily-summarize.yml`
- Modify: `.github/workflows/daily-sync-kb.yml`
- Modify: `.github/workflows/deploy-pages.yml`

**Step 1: Update `daily-summarize.yml`**

Remove the `git add data/` and commit/push steps. The workflow should:
1. Fetch new videos
2. Transcribe and summarize
3. Save to local `data/` (ephemeral, on CI runner)
4. Trigger sync workflow (which uploads to Vector Store)
5. Do NOT commit data

Find and remove or modify the commit step. Keep only `git add data/index.json` since that's the only file that stays.

```yaml
      - name: Commit index.json only
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/index.json
          if git diff --staged --quiet; then
            echo "No changes to commit"
          else
            git commit -m "chore: update video index $(date +%Y-%m-%d)"
            git pull --rebase || true
            git push
          fi
```

**Step 2: Update `daily-sync-kb.yml`**

Remove the entire "Commit and push data changes" step (lines 52-62). Remove the "Deploy to GitHub Pages" steps (lines 64-80) since data is no longer needed in Pages.

The workflow becomes:
1. Checkout
2. Setup Python
3. Install deps
4. Fetch Google Sheets (save to ephemeral `data/sheets/`)
5. Sync to Vector Store (reads from `data/`, uploads to OpenAI)
6. Done — no commit, no deploy

```yaml
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: pip install -r scripts/requirements.txt

      # Disabled: X API rate limit reached
      # - name: Fetch tweets
      #   run: cd scripts/dify_sync && python3 fetch_tweets.py
      #   continue-on-error: true

      - name: Fetch Google Sheets
        run: cd scripts/dify_sync && python3 fetch_sheets.py
        continue-on-error: true

      - name: Sync to vector store
        run: cd scripts/dify_sync && python3 sync_vector_store.py
```

**Step 3: Update `deploy-pages.yml`**

Remove `cp -r data site/data` step. The site deploys without any data directory.

```yaml
    steps:
      - uses: actions/checkout@v4

      - name: Setup Pages
        uses: actions/configure-pages@v4

      - name: Upload artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: site

      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
```

**Step 4: Commit**

```bash
git add .github/workflows/daily-summarize.yml .github/workflows/daily-sync-kb.yml .github/workflows/deploy-pages.yml
git commit -m "fix: stop committing data to repo, deploy site without data"
```

---

### Task 3: Remove sensitive data from repo and update `.gitignore`

**Files:**
- Modify: `.gitignore`
- Delete from git: `data/summaries/`, `data/sheets/`, `data/tweets/`, `data/mcp/`, `data/test-reports/`, `data/docs/`
- Keep in git: `data/index.json`

**Step 1: Update `.gitignore`**

Add these lines:
```
# Sensitive data — never commit
data/summaries/
data/sheets/
data/tweets/
data/mcp/
data/test-reports/
data/docs/
data/uploads/
```

**Step 2: Remove tracked data files from git (keep local copies)**

```bash
git rm -r --cached data/summaries/ data/sheets/ data/tweets/ data/mcp/ data/test-reports/ data/docs/ 2>/dev/null || true
```

The `--cached` flag removes from git tracking but keeps local files on disk.

**Step 3: Verify `data/index.json` is still tracked**

```bash
git status
# Should show: data/index.json is still tracked
# Should show: deleted (from index) for summaries/, sheets/, etc.
```

**Step 4: Commit**

```bash
git add .gitignore
git commit -m "security: remove sensitive data from repo, add to gitignore

Remove portfolio data, chatroom articles, tweets, and summaries from
git tracking. Only data/index.json (public YouTube metadata) remains.
Data now lives exclusively in OpenAI Vector Store."
```

---

### Task 4: Update Dockerfile and render.yaml for new Docker context

**Files:**
- Modify: `render.yaml`
- Modify: `scripts/dify_sync/Dockerfile`

**Step 1: Update `render.yaml` Docker context**

```yaml
services:
  - type: web
    name: talk-ai-api
    runtime: docker
    dockerfilePath: scripts/dify_sync/Dockerfile
    dockerContext: .
    region: singapore
    plan: free
    envVars:
      - key: OPENAI_API_KEY
        sync: false
      - key: VECTOR_STORE_ID
        sync: false
```

**Step 2: Update Dockerfile paths**

Read the current Dockerfile first, then update COPY paths to be relative to repo root (new context):

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY scripts/dify_sync/requirements-api.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY scripts/dify_sync/web_demo.py scripts/dify_sync/config.py ./
COPY data/index.json ./data/index.json
EXPOSE 8080
CMD ["python", "web_demo.py"]
```

**Step 3: Commit**

```bash
git add render.yaml scripts/dify_sync/Dockerfile
git commit -m "build: update Docker context to repo root, include index.json"
```

---

### Task 5: Update `daily-summarize.yml` to rebuild index.json and commit only that

The daily summarize workflow produces new video summaries. It needs to:
1. Still generate summaries (saved to ephemeral disk)
2. Update `data/index.json` with new video metadata
3. Commit ONLY `data/index.json`
4. Trigger the sync-kb workflow for Vector Store upload

**Files:**
- Modify: `.github/workflows/daily-summarize.yml`

**Step 1: Read current workflow**

Read `.github/workflows/daily-summarize.yml` to understand the current commit step.

**Step 2: Change git add to only include index.json**

Replace:
```yaml
git add data/
```
With:
```yaml
git add data/index.json
```

And update the commit message:
```yaml
git commit -m "chore: update video index $(date +%Y-%m-%d)"
```

**Step 3: Commit**

```bash
git add .github/workflows/daily-summarize.yml
git commit -m "fix: daily summarize only commits index.json, not full data"
```

---

### Task 6: Handle summary page without local JSON files

The summary page (`site/summary.html`) currently expects a full JSON object with `summary.zh-Hant.keyPoints`, `tickers`, etc. The `/api/summary` endpoint returns a GPT-generated text response from Vector Store search, which won't have the same structured JSON.

**Two options:**
- **Option A:** Rewrite summary page to render plain text from API (simpler, loses key points timeline)
- **Option B:** Store summaries as JSON alongside Markdown in Vector Store, retrieve by filename

**Recommended: Option A** — the summary page renders the AI-returned text. Key points and tickers are included in the Markdown that Vector Store searches, so the AI response will contain them as text.

**Files:**
- Modify: `site/summary.html`
- Modify: `site/js/app.js` (the `fetchSummary` return format changes)

**Step 1: Update `fetchSummary` in `app.js`**

The API returns `{id, date, summary}` where `summary` is plain text. The summary page needs to handle this new format.

```javascript
function fetchSummary(id, publishedAt) {
    var params = 'id=' + encodeURIComponent(id);
    if (publishedAt) params += '&date=' + encodeURIComponent(publishedAt);
    return fetch(API_BASE + '/api/summary?' + params)
        .then(function (res) {
            if (!res.ok) throw new Error('HTTP ' + res.status);
            return res.json();
        })
        .then(function (data) {
            // Normalize: API returns {id, date, summary} as text
            // Convert to the format the summary page expects
            return {
                id: data.id,
                videoId: data.id,
                publishedAt: data.date,
                title: '', // Will be filled from index
                summary: {
                    'zh-Hant': { paragraph: data.summary, keyPoints: [], tags: [] },
                    'zh-Hans': { paragraph: data.summary, keyPoints: [], tags: [] }
                },
                tickers: []
            };
        });
}
```

**Step 2: Commit**

```bash
git add site/js/app.js site/summary.html
git commit -m "feat: summary page uses API response instead of static JSON"
```

---

### Task 7: Push all changes and verify deployment

**Step 1: Push to remote**

```bash
git push origin main
```

**Step 2: Verify GitHub Pages deployment**

Check that GitHub Pages deploys successfully without `data/`:
```bash
gh run list --workflow=deploy-pages.yml --limit 1
```

**Step 3: Verify Render deployment**

Wait for Render to rebuild with new Dockerfile, then test:
```bash
curl -s https://talk-library.onrender.com/health
curl -s https://talk-library.onrender.com/api/videos | head -c 200
```

**Step 4: Test on phone**

Visit `https://cyt9999.github.io/talk-library/` on phone:
- Home page should load video list from API
- Chat page should work as before
- Summary page should load via API

---

### Task 8: Verify no sensitive data remains in git history

**Step 1: Check current repo state**

```bash
git log --oneline --all -- data/sheets/ data/mcp/ data/tweets/ | head -20
```

If sensitive data exists in git history and you want to fully purge it:

```bash
# Optional: only if full history purge is needed
git filter-branch --force --index-filter \
  'git rm -r --cached --ignore-unmatch data/sheets/ data/mcp/ data/tweets/ data/summaries/' \
  --prune-empty -- --all
git push origin main --force
```

**Note:** Force push rewrites history. Only do this if the team agrees. For now, just removing from HEAD and `.gitignore` is sufficient — the old data in history will eventually be pruned.

**Step 2: Final verification**

```bash
ls data/  # Should only show index.json (and local dev files not tracked)
git ls-files data/  # Should only show data/index.json
```

**Step 3: Commit (if any cleanup needed)**

```bash
git commit -m "chore: verify data security cleanup complete"
```
