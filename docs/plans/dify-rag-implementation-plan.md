# 投資Talk君 AI — Dify RAG 實作計畫

> **目標**：在 2026 年 3 月 31 日前，部署一個可運作的 Q&A 機器人 MVP。使用者提問後，機器人從 Talk君 的內容中回答，並附上引用來源。
>
> **預算目標**：每月 GCP 費用控制在 US$30–50 以內（不含 OpenAI API 費用）。
>
> **讀者須知**：本文件為逐步操作手冊。每個指令皆可直接複製貼上執行。UI 操作會標示精確的按鈕名稱與導覽路徑。

---

## 目錄

- [Phase A — GCP VM 建置 + Docker + Dify 部署](#phase-a--gcp-vm-建置--docker--dify-部署)
- [Phase B — Dify 基本設定 + 知識庫結構](#phase-b--dify-基本設定--知識庫結構)
- [Phase C — 資料匯入與同步管線](#phase-c--資料匯入與同步管線)
- [Phase D — Q&A 聊天機器人工作流程](#phase-d--qa-聊天機器人工作流程)
- [Phase E — 測試與迭代](#phase-e--測試與迭代)
- [Phase F — API 端點對外開放](#phase-f--api-端點對外開放)
- [附錄 — 成本估算彙整](#附錄--成本估算彙整)
- [附錄 — Phase 2 擴充藍圖](#附錄--phase-2-擴充藍圖)

---

## Phase A — GCP VM 建置 + Docker + Dify 部署

**預估時間**：3–4 小時（含等待安裝的時間）
**前置條件**：
- GCP 專案 `overseas-author` 已啟用帳單
- 你可以登入 Google Cloud Console（https://console.cloud.google.com）
- 你有本機的終端機（Windows Terminal、PowerShell、或 Git Bash 皆可）

**費用影響**：
- `e2-medium`（2 vCPU / 4 GB RAM）：約 US$24.27/月（asia-east1）
- 30 GB 標準永久磁碟：約 US$1.20/月
- 靜態外部 IP（使用中不額外收費，未掛載才收費）
- **合計約 US$25–27/月**

---

### A-1. 建立 Compute Engine VM

1. 開啟瀏覽器，前往：
   ```
   https://console.cloud.google.com/compute/instancesAdd?project=overseas-author
   ```

2. 填入以下設定：

   | 欄位 | 值 |
   |---|---|
   | **名稱** | `dify-server` |
   | **區域 (Region)** | `asia-east1 (Taiwan)` |
   | **可用區 (Zone)** | `asia-east1-b` |
   | **機器系列** | `General purpose` |
   | **系列** | `E2` |
   | **機器類型** | `e2-medium (2 vCPU, 4 GB memory)` |

   > **為何選 e2-medium？** Dify 使用 Docker Compose 執行多個容器（API server、Web frontend、PostgreSQL、Redis、Weaviate 向量庫）。4 GB RAM 是最低可用門檻。如果日後負載增加，可以隨時升級為 `e2-standard-2`（2 vCPU / 8 GB RAM，約 US$48/月），不需重建。

3. 在「**開機磁碟 (Boot disk)**」區塊，點擊「**變更 (CHANGE)**」：

   | 欄位 | 值 |
   |---|---|
   | **作業系統** | `Ubuntu` |
   | **版本** | `Ubuntu 22.04 LTS` (x86/64) |
   | **開機磁碟類型** | `Standard persistent disk`（不要選 SSD，節省成本） |
   | **大小 (GB)** | `30` |

   點擊「**選取 (SELECT)**」。

4. 在「**防火牆 (Firewall)**」區塊，勾選：
   - [x] **允許 HTTP 流量**
   - [x] **允許 HTTPS 流量**

5. 展開「**進階選項 (Advanced options)** > **網路 (Networking)**」：
   - 在「**網路介面 (Network interfaces)**」點擊 `default` 旁的編輯按鈕
   - 在「**外部 IPv4 位址 (External IPv4 address)**」下拉選單，選擇「**建立 IP 位址 (CREATE IP ADDRESS)**」
   - 名稱輸入：`dify-static-ip`
   - 點擊「**保留 (RESERVE)**」
   - 記下此 IP 位址（後面稱為 `YOUR_VM_IP`）

6. 點擊頁面最下方的「**建立 (CREATE)**」按鈕。

7. 等待約 30–60 秒，VM 狀態變為綠色勾勾。

---

### A-2. 建立防火牆規則（開放 Dify 預設的 80 port）

Dify 的 Web UI 預設跑在 port 80。GCP 預設的 HTTP 防火牆規則已允許 port 80，但我們要額外開放 port 443（HTTPS）以備日後使用。

在 Cloud Console 中：

1. 前往：
   ```
   https://console.cloud.google.com/networking/firewalls/add?project=overseas-author
   ```

2. 填入以下設定：

   | 欄位 | 值 |
   |---|---|
   | **名稱** | `allow-dify-ports` |
   | **網路** | `default` |
   | **優先順序** | `1000` |
   | **流量方向** | `Ingress（輸入）` |
   | **相符時的動作** | `Allow（允許）` |
   | **目標** | `All instances in the network` |
   | **來源 IPv4 範圍** | `0.0.0.0/0` |
   | **通訊協定和連接埠** | 選「指定的通訊協定和連接埠」，勾選 `tcp`，填入 `80,443` |

3. 點擊「**建立 (CREATE)**」。

> **安全性備註**：MVP 階段我們先開放全部 IP。Phase 2 可改為只允許特定 IP 或掛上 Cloud IAP。

---

### A-3. SSH 連入 VM 並安裝 Docker

1. 回到 VM 列表頁面：
   ```
   https://console.cloud.google.com/compute/instances?project=overseas-author
   ```

2. 找到 `dify-server`，點擊右邊的「**SSH**」按鈕。這會開啟一個瀏覽器內的 SSH 終端視窗。

3. 在 SSH 終端中，依序執行以下指令（一次一行，或全部複製貼上）：

```bash
# === 更新系統套件 ===
sudo apt-get update && sudo apt-get upgrade -y
```

```bash
# === 安裝 Docker ===
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

```bash
# === 讓當前使用者不需要 sudo 就能跑 Docker ===
sudo usermod -aG docker $USER
newgrp docker
```

4. 驗證 Docker 安裝成功：

```bash
docker --version
# 預期輸出類似: Docker version 27.x.x, build xxxxxxx

docker compose version
# 預期輸出類似: Docker Compose version v2.x.x
```

---

### A-4. 部署 Dify（Docker Compose）

```bash
# === 下載 Dify 原始碼 ===
cd ~
git clone https://github.com/langgenius/dify.git
cd dify/docker
```

```bash
# === 複製環境設定檔 ===
cp .env.example .env
```

在啟動之前，我們需要修改一個關鍵設定 — 把 Dify 的密鑰換成你自己的隨機值（安全性考量）：

```bash
# === 產生隨機密鑰並寫入 .env ===
SECRET_KEY=$(openssl rand -hex 32)
sed -i "s/^SECRET_KEY=.*/SECRET_KEY=${SECRET_KEY}/" .env

# 確認密鑰已更新
grep "^SECRET_KEY=" .env
```

啟動 Dify：

```bash
docker compose up -d
```

> **這一步需要等待 3–8 分鐘**，Docker 會下載所有映像檔（約 3–4 GB）。如果網路較慢可能更久。

查看容器狀態：

```bash
docker compose ps
```

你應該看到大約 8–10 個容器都是 `Up` 或 `running` 狀態。關鍵容器包括：
- `docker-api-1` — Dify 後端 API
- `docker-web-1` — Dify 前端
- `docker-db-1` — PostgreSQL 資料庫
- `docker-redis-1` — Redis 快取
- `docker-weaviate-1` — 向量資料庫

如果有容器不斷重啟，查看 log：
```bash
docker compose logs api --tail 50
```

---

### A-5. 驗證 Dify 可存取

1. 開啟瀏覽器，輸入：
   ```
   http://YOUR_VM_IP
   ```
   （把 `YOUR_VM_IP` 換成你在 A-1 步驟 5 記下的 IP 位址）

2. 你應該看到 Dify 的初始設定頁面，要求你建立管理員帳號。

3. 填入：

   | 欄位 | 建議值 |
   |---|---|
   | **Email** | 你的常用 email |
   | **使用者名稱** | `admin` |
   | **密碼** | 選一個強密碼，記下來 |

4. 點擊「**設定 (Set up)**」或「**Sign Up**」。

5. 你現在應該看到 Dify 的主控台（Dashboard）。

---

### A-6. 設定 VM 自動啟動 Dify（重開機保護）

如果 VM 重啟，Docker 預設會自動啟動已設定 `restart: always` 的容器。Dify 的 docker-compose.yml 已內建此設定。但為保險起見，我們新增一個 systemd 服務：

```bash
sudo tee /etc/systemd/system/dify.service > /dev/null <<'EOF'
[Unit]
Description=Dify Docker Compose
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/$USER/dify/docker
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
User=$USER

[Install]
WantedBy=multi-user.target
EOF

# 把 $USER 替換成你的實際使用者名稱
sudo sed -i "s/\$USER/$(whoami)/g" /etc/systemd/system/dify.service

sudo systemctl daemon-reload
sudo systemctl enable dify.service
```

---

### Phase A 檢查點

- [ ] `docker compose ps` 顯示所有容器 running
- [ ] 瀏覽器開啟 `http://YOUR_VM_IP` 可看到 Dify 介面
- [ ] 已建立管理員帳號並成功登入
- [ ] VM 的靜態 IP 已記錄

---

## Phase B — Dify 基本設定 + 知識庫結構

**預估時間**：1–2 小時
**前置條件**：Phase A 完成，Dify 可在瀏覽器中存取
**費用影響**：無額外費用（此階段只是設定）

---

### B-1. 連接 OpenAI API Key

1. 在 Dify 主控台，點擊右上角的**頭像圖示**，選擇「**Settings（設定）**」。

2. 在左側選單中，點擊「**Model Provider（模型供應商）**」。

3. 找到「**OpenAI**」卡片，點擊「**Set up（設定）**」或「**Add Model（新增模型）**」。

4. 輸入你的 OpenAI API Key：
   - **API Key**：貼上你的 `sk-...` 開頭的 API Key
   - 點擊「**Save（儲存）**」

5. 驗證：在 OpenAI 卡片上應該顯示綠色的 `Active` 或 `Connected` 狀態。

6. 設定預設模型：
   - 在 Settings 頁面找到「**System Model Settings（系統模型設定）**」或在 Model Provider 頁面上方
   - **System Inference Model**：選擇 `gpt-4o`
   - **Embedding Model**：選擇 `text-embedding-3-small`（比 `text-embedding-3-large` 便宜 5 倍，效果已足夠）
   - 點擊「**Save**」

> **為何用 `text-embedding-3-small`？** 每百萬 token 只要 US$0.02，而 `text-embedding-3-large` 要 US$0.13。對 MVP 來說效果差異可忽略。

---

### B-2. 建立知識庫結構

我們將建立 **4 個獨立的知識庫**，對應不同的資料來源。分開建立的好處是：
- 可以針對不同來源設定不同的索引策略
- 在 RAG 查詢時可以控制優先順序
- 日後新增來源只需建新的知識庫

#### 知識庫 1：YouTube 影片（核心內容）

1. 在 Dify 主控台上方，點擊「**Knowledge（知識庫）**」頁籤。

2. 點擊「**Create Knowledge（建立知識庫）**」。

3. 填入：
   - **Knowledge Name**：`YouTube影片分析`
   - **Description**：`Talk君YouTube頻道的影片逐字稿與結構化摘要，包含股票分析、總經解讀、市場觀點。`

4. 點擊「**Create（建立）**」。

5. 先不要上傳檔案（Phase C 才做），點擊「**Settings（設定）**」齒輪圖示或進入知識庫後點擊「**Settings**」頁籤：

   | 設定 | 值 |
   |---|---|
   | **Indexing Mode** | `High Quality`（使用 Embedding 模型做向量索引） |
   | **Embedding Model** | `text-embedding-3-small (OpenAI)` |
   | **Retrieval Setting** | `Hybrid Search`（結合向量搜尋 + 全文搜尋，效果最好） |

6. 點擊「**Save**」。

#### 知識庫 2：社團貼文（最即時的信號）

重複步驟 2–6，但使用：
- **Knowledge Name**：`社團貼文信號`
- **Description**：`同學會社團的短文與交易信號，包含開倉、平倉、市場即時觀點。更新頻率最高，內容最即時。`

#### 知識庫 3：Google Sheets 數據

重複步驟 2–6，但使用：
- **Knowledge Name**：`持倉與總經數據`
- **Description**：`Talk君的持倉績效、總經公告、持倉Beta、資料來源等 Google Sheets 數據。反映當前持倉狀態與宏觀指標。`

#### 知識庫 4：X (Twitter) 貼文

重複步驟 2–6，但使用：
- **Knowledge Name**：`X平台短評`
- **Description**：`Talk君在X平台(@TJ_Research)發布的短篇市場評論與觀點。`

---

### B-3. 記錄知識庫 ID

每個知識庫建立後，Dify 會賦予一個唯一的 dataset ID。Phase C 的自動化同步腳本需要這些 ID。

取得方式：
1. 進入每個知識庫
2. 看瀏覽器網址列，格式為：`http://YOUR_VM_IP/datasets/DATASET_ID/documents`
3. 複製 `DATASET_ID` 部分

把四個 ID 記在一個安全的地方：

```
YouTube影片分析:     DATASET_ID_YOUTUBE = _______________
社團貼文信號:        DATASET_ID_COMMUNITY = _______________
持倉與總經數據:      DATASET_ID_SHEETS = _______________
X平台短評:          DATASET_ID_TWITTER = _______________
```

---

### Phase B 檢查點

- [ ] OpenAI API Key 顯示 Active / Connected
- [ ] 預設 Embedding 模型設定為 `text-embedding-3-small`
- [ ] 預設推理模型設定為 `gpt-4o`
- [ ] 4 個知識庫已建立（YouTube、社團、Sheets、Twitter）
- [ ] 4 個知識庫的 Dataset ID 已記錄
- [ ] 每個知識庫的 Indexing Mode 為 High Quality，Retrieval 為 Hybrid Search

---

## Phase C — 資料匯入與同步管線

**預估時間**：6–10 小時（分多天進行）
**前置條件**：Phase B 完成
**費用影響**：
- OpenAI Embedding 費用：初次匯入約 US$0.05–0.20（依資料量）
- 每日同步的 Embedding 費用：約 US$0.01–0.05/天

---

### C-1. 取得 Dify API Key（用於自動化上傳）

1. 在 Dify 主控台，點擊右上角**頭像** > **Settings**。
2. 在左側選單點擊「**API Keys**」（在 Account 區塊下）或「**API Access**」。

   > **注意**：Dify 有兩種 API Key — 帳號層級的（用於 Dataset API）和應用程式層級的（用於聊天 API）。這裡我們要的是**帳號層級**的 Dataset API Key。

3. 在 Knowledge 頁面中，點擊右上角你的頭像旁邊的「**API**」字樣（或在 Settings > API Keys 中），找到「**Dataset API**」區塊。
4. 點擊「**Create new secret key**」。
5. 複製並安全保存此 Key（以 `dataset-` 開頭）。

後續稱這個 Key 為 `DIFY_API_KEY`。

---

### C-2. 匯入 YouTube 影片資料（首次批量上傳）

我們要把 `/data/summaries/` 下的 JSON 檔轉成 Dify 知識庫可讀的格式。Dify 的知識庫支援上傳 `.txt`、`.md`、`.pdf` 等檔案。最佳做法是把每部影片轉成一個 Markdown 文件。

#### 步驟 1：在 VM 上建立轉換腳本

SSH 進入你的 VM（點擊 GCP Console 的 SSH 按鈕），然後：

```bash
mkdir -p ~/dify-sync
cd ~/dify-sync
```

建立轉換腳本：

```bash
cat > ~/dify-sync/convert_youtube_to_md.py << 'PYEOF'
#!/usr/bin/env python3
"""
將 talk_library 的 YouTube summary JSON 轉換為 Dify 知識庫可用的 Markdown 文件。
每部影片產生一個 .md 檔案。
"""

import json
import os
import sys
import glob


def json_to_markdown(data):
    """將單一 summary JSON 轉換為 Markdown 字串。"""
    # 優先使用繁體中文
    lang = 'zh-Hant' if 'zh-Hant' in data.get('summary', {}) else 'zh-Hans'
    summary = data['summary'][lang]

    lines = []

    # 標題與元資料
    title = data.get('title', '未知標題')
    date = data.get('publishedAt', '未知日期')
    channel = data.get('channelName', '未知頻道')
    video_url = data.get('videoUrl', '')
    video_id = data.get('videoId', '')
    duration_sec = data.get('duration', 0)
    duration_min = duration_sec // 60

    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"- **來源**: YouTube 影片")
    lines.append(f"- **頻道**: {channel}")
    lines.append(f"- **日期**: {date}")
    lines.append(f"- **時長**: {duration_min} 分鐘")
    if video_url:
        lines.append(f"- **連結**: {video_url}")
    lines.append(f"- **影片 ID**: {video_id}")
    lines.append("")

    # 標籤
    tags = summary.get('tags', [])
    if tags:
        lines.append(f"**標籤**: {', '.join(tags)}")
        lines.append("")

    # 總結段落
    paragraph = summary.get('paragraph', '')
    if paragraph:
        lines.append("## 內容摘要")
        lines.append("")
        lines.append(paragraph)
        lines.append("")

    # 關鍵要點
    key_points = summary.get('keyPoints', [])
    if key_points:
        lines.append("## 關鍵要點")
        lines.append("")
        for i, kp in enumerate(key_points, 1):
            ts = kp.get('timestamp', 0)
            minutes = ts // 60
            seconds = ts % 60
            text = kp.get('text', '')
            ts_str = f"[{minutes:02d}:{seconds:02d}]"
            lines.append(f"{i}. {ts_str} {text}")
        lines.append("")

    # 相關股票
    tickers = data.get('tickers', [])
    if tickers:
        lines.append("## 提及股票")
        lines.append("")
        for t in tickers:
            symbol = t.get('symbol', '')
            name = t.get('name', '')
            sentiment = t.get('sentiment', 'neutral')
            sentiment_label = {'bullish': '看多', 'bearish': '看空', 'neutral': '中性'}.get(sentiment, sentiment)
            lines.append(f"- **{symbol}** ({name}) — 觀點: {sentiment_label}")

            mentions = t.get('mentions', [])
            for m in mentions:
                context = m.get('context', '')
                start = m.get('start', 0)
                end = m.get('end', 0)
                lines.append(f"  - [{start//60:02d}:{start%60:02d}–{end//60:02d}:{end%60:02d}] {context}")
        lines.append("")

    return "\n".join(lines)


def convert_directory(input_dir, output_dir):
    """轉換目錄下所有 JSON 為 Markdown。"""
    os.makedirs(output_dir, exist_ok=True)

    json_files = sorted(glob.glob(os.path.join(input_dir, "*.json")))
    converted = 0

    for filepath in json_files:
        filename = os.path.basename(filepath)
        if filename == "index.json" or filename == "channels.json":
            continue

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            md_content = json_to_markdown(data)
            md_filename = filename.replace('.json', '.md')
            md_path = os.path.join(output_dir, md_filename)

            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(md_content)

            print(f"OK: {filename} -> {md_filename}")
            converted += 1

        except Exception as e:
            print(f"ERROR: {filename}: {e}", file=sys.stderr)

    print(f"\n共轉換 {converted} 個檔案到 {output_dir}")
    return converted


if __name__ == '__main__':
    input_dir = sys.argv[1] if len(sys.argv) > 1 else './summaries'
    output_dir = sys.argv[2] if len(sys.argv) > 2 else './md_output/youtube'
    convert_directory(input_dir, output_dir)
PYEOF

chmod +x ~/dify-sync/convert_youtube_to_md.py
```

#### 步驟 2：把 GitHub Repo 的 JSON 複製到 VM

```bash
cd ~/dify-sync

# 從你的 GitHub repo clone（只需 data 目錄）
git clone --depth 1 --filter=blob:none --sparse \
  https://github.com/YOUR_USERNAME/talk_library.git repo-data
cd repo-data
git sparse-checkout set data/summaries
cd ..

# 或者，如果 repo 不大，直接 clone 整個：
# git clone https://github.com/YOUR_USERNAME/talk_library.git repo-data
```

> **重要**：把 `YOUR_USERNAME` 替換成你的 GitHub 使用者名稱。如果 repo 是 private，你需要先設定 GitHub Personal Access Token (PAT)：
> ```bash
> git clone https://YOUR_PAT@github.com/YOUR_USERNAME/talk_library.git repo-data
> ```

#### 步驟 3：執行轉換

```bash
cd ~/dify-sync
python3 convert_youtube_to_md.py repo-data/data/summaries ./md_output/youtube
```

你應該看到每個 JSON 檔案都成功轉換的訊息。

#### 步驟 4：透過 Dify API 批量上傳

建立上傳腳本：

```bash
cat > ~/dify-sync/upload_to_dify.py << 'PYEOF'
#!/usr/bin/env python3
"""
批量上傳 Markdown 文件到 Dify 知識庫。
使用 Dify Dataset API。
"""

import os
import sys
import time
import requests
import glob


DIFY_BASE_URL = "http://localhost/v1"  # VM 本機的 Dify API


def upload_files(api_key, dataset_id, file_dir, file_pattern="*.md"):
    """上傳目錄下所有符合條件的檔案到指定知識庫。"""
    headers = {
        "Authorization": f"Bearer {api_key}"
    }

    files_to_upload = sorted(glob.glob(os.path.join(file_dir, file_pattern)))
    print(f"找到 {len(files_to_upload)} 個檔案待上傳")

    success = 0
    failed = 0

    for filepath in files_to_upload:
        filename = os.path.basename(filepath)
        print(f"上傳中: {filename}...", end=" ", flush=True)

        try:
            with open(filepath, 'rb') as f:
                resp = requests.post(
                    f"{DIFY_BASE_URL}/datasets/{dataset_id}/document/create-by-file",
                    headers=headers,
                    files={
                        "file": (filename, f, "text/markdown")
                    },
                    data={
                        "data": '{"indexing_technique": "high_quality", "process_rule": {"mode": "automatic"}}'
                    }
                )

            if resp.status_code in (200, 201):
                print("OK")
                success += 1
            else:
                print(f"FAILED ({resp.status_code}): {resp.text[:200]}")
                failed += 1

            # 每個上傳之間暫停 1 秒，避免速率限制
            time.sleep(1)

        except Exception as e:
            print(f"ERROR: {e}")
            failed += 1

    print(f"\n上傳完成: {success} 成功, {failed} 失敗")
    return success, failed


if __name__ == '__main__':
    api_key = os.environ.get("DIFY_API_KEY")
    if not api_key:
        print("請設定環境變數 DIFY_API_KEY", file=sys.stderr)
        print("用法: DIFY_API_KEY=your-key python3 upload_to_dify.py <dataset_id> <file_dir>", file=sys.stderr)
        sys.exit(1)

    if len(sys.argv) < 3:
        print("用法: DIFY_API_KEY=your-key python3 upload_to_dify.py <dataset_id> <file_dir>", file=sys.stderr)
        sys.exit(1)

    dataset_id = sys.argv[1]
    file_dir = sys.argv[2]
    pattern = sys.argv[3] if len(sys.argv) > 3 else "*.md"

    upload_files(api_key, dataset_id, file_dir, pattern)
PYEOF

chmod +x ~/dify-sync/upload_to_dify.py
```

安裝 Python requests（如果尚未安裝）：

```bash
sudo apt-get install -y python3-pip
pip3 install requests
```

執行上傳：

```bash
cd ~/dify-sync

# 把下面的值替換成你的實際值
export DIFY_API_KEY="dataset-xxxxxxxxxxxxxxxx"
export DATASET_ID_YOUTUBE="你的YouTube知識庫ID"

python3 upload_to_dify.py "$DATASET_ID_YOUTUBE" ./md_output/youtube
```

#### 步驟 5：在 Dify UI 中驗證

1. 回到 Dify 瀏覽器介面
2. 點擊「**Knowledge**」 > 「**YouTube影片分析**」
3. 你應該看到所有上傳的文件列表
4. 點擊任一文件，確認內容完整、已被索引（狀態為 `Available` 或 `Completed`）

---

### C-3. 匯入社團貼文（從 Google Sheet）

社團貼文存放在 Google Sheet「爬蟲-投資 talk 君 2025 文章」。我們需要：
1. 從 Google Sheet 匯出資料
2. 轉成 Dify 可用的格式
3. 上傳到知識庫

#### 步驟 1：設定 Google Sheets API 存取

1. 前往 Google Cloud Console：
   ```
   https://console.cloud.google.com/apis/library/sheets.googleapis.com?project=overseas-author
   ```

2. 點擊「**啟用 (ENABLE)**」Google Sheets API。

3. 建立服務帳號：
   ```
   https://console.cloud.google.com/iam-admin/serviceaccounts/create?project=overseas-author
   ```

   | 欄位 | 值 |
   |---|---|
   | **服務帳號名稱** | `dify-sheets-reader` |
   | **服務帳號 ID** | `dify-sheets-reader` |
   | **說明** | `Read-only access to Google Sheets for Dify knowledge base sync` |

4. 點擊「**建立並繼續**」。

5. 在角色選擇頁面，先跳過（不需要 GCP 角色），直接點「**繼續**」，然後「**完成**」。

6. 回到服務帳號列表，找到 `dify-sheets-reader`，點擊它。

7. 點擊「**金鑰 (Keys)**」頁籤 > 「**新增金鑰 (ADD KEY)**」 > 「**建立新金鑰 (Create new key)**」> 選「**JSON**」> 「**建立 (CREATE)**」。

8. 瀏覽器會自動下載一個 `.json` 金鑰檔案。**安全保存此檔案**。

9. **重要**：開啟你的每一個 Google Sheet，點擊「**共用 (Share)**」，將服務帳號的 email（格式為 `dify-sheets-reader@overseas-author.iam.gserviceaccount.com`）加入為「**檢視者 (Viewer)**」。

#### 步驟 2：上傳服務帳號金鑰到 VM

在 GCP SSH 終端中：

```bash
mkdir -p ~/dify-sync/credentials
```

然後把下載的 JSON 金鑰內容貼入（方法一：用 nano 編輯器）：

```bash
nano ~/dify-sync/credentials/gcp-service-account.json
# 在本地電腦用文字編輯器開啟下載的 JSON 檔案
# 全選複製，然後在 nano 中右鍵貼上
# 按 Ctrl+O 儲存，按 Ctrl+X 離開
```

或（方法二：用 gcloud 從本機上傳）：
```bash
# 在你的本地電腦終端執行（不是 VM）：
gcloud compute scp ~/Downloads/你的金鑰檔名.json \
  dify-server:~/dify-sync/credentials/gcp-service-account.json \
  --zone=asia-east1-b --project=overseas-author
```

#### 步驟 3：建立 Google Sheets 同步腳本

回到 VM 的 SSH 終端：

```bash
pip3 install google-api-python-client google-auth
```

```bash
cat > ~/dify-sync/sync_sheets.py << 'PYEOF'
#!/usr/bin/env python3
"""
從 Google Sheets 讀取資料，轉換成 Markdown，上傳到 Dify 知識庫。
"""

import json
import os
import sys
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build

# === 設定區 — 請填入你的 Sheet ID ===
# Sheet ID 在 Google Sheet 網址中：
# https://docs.google.com/spreadsheets/d/SHEET_ID_HERE/edit
SHEETS_CONFIG = {
    "社團貼文": {
        "sheet_id": "YOUR_SHEET_ID_社團",           # ← 替換
        "range": "A:Z",                              # 讀取所有欄位
        "output_file": "community_posts.md",
        "dataset_type": "community"                   # 對應 DATASET_ID_COMMUNITY
    },
    "總經公告": {
        "sheet_id": "YOUR_SHEET_ID_總經",           # ← 替換
        "range": "A:Z",
        "output_file": "macro_indicators.md",
        "dataset_type": "sheets"
    },
    "持倉績效": {
        "sheet_id": "YOUR_SHEET_ID_持倉績效",      # ← 替換
        "range": "A:Z",
        "output_file": "portfolio_performance.md",
        "dataset_type": "sheets"
    },
    "資料來源": {
        "sheet_id": "YOUR_SHEET_ID_資料來源",      # ← 替換
        "range": "A:Z",
        "output_file": "market_data_sources.md",
        "dataset_type": "sheets"
    },
    "持倉Beta": {
        "sheet_id": "YOUR_SHEET_ID_Beta",           # ← 替換
        "range": "A:Z",
        "output_file": "portfolio_beta.md",
        "dataset_type": "sheets"
    }
}

CREDENTIALS_PATH = os.path.expanduser("~/dify-sync/credentials/gcp-service-account.json")
OUTPUT_DIR = os.path.expanduser("~/dify-sync/md_output/sheets")


def get_sheets_service():
    """建立 Google Sheets API 服務。"""
    creds = service_account.Credentials.from_service_account_file(
        CREDENTIALS_PATH,
        scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
    )
    return build('sheets', 'v4', credentials=creds)


def fetch_sheet_data(service, sheet_id, range_name):
    """從指定 Sheet 讀取資料。"""
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=range_name
    ).execute()
    return result.get('values', [])


def rows_to_markdown(sheet_name, rows):
    """將 Sheet 的列資料轉成 Markdown 表格或列表。"""
    if not rows:
        return f"# {sheet_name}\n\n（無資料）\n"

    lines = []
    lines.append(f"# {sheet_name}")
    lines.append(f"")
    lines.append(f"- **資料來源**: Google Sheets")
    lines.append(f"- **最後更新**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"- **總筆數**: {len(rows) - 1}")  # 扣掉標題列
    lines.append("")

    # 第一列當作標題
    headers = rows[0] if rows else []
    data_rows = rows[1:] if len(rows) > 1 else []

    if not headers:
        return "\n".join(lines) + "\n（空白表格）\n"

    # 如果資料筆數很多（如社團貼文），用列表格式而非表格
    if len(data_rows) > 50:
        # 列表格式 — 每筆資料一個段落
        for i, row in enumerate(data_rows):
            lines.append(f"## 第 {i + 1} 筆")
            for j, header in enumerate(headers):
                value = row[j] if j < len(row) else ""
                if value:
                    lines.append(f"- **{header}**: {value}")
            lines.append("")
    else:
        # Markdown 表格格式
        # 表頭
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

        for row in data_rows:
            # 確保每列的欄數與標題相同
            padded_row = row + [""] * (len(headers) - len(row))
            cells = [cell.replace("|", "\\|").replace("\n", " ") for cell in padded_row[:len(headers)]]
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")

    return "\n".join(lines)


def community_posts_to_markdown(sheet_name, rows):
    """
    社團貼文的特殊處理：每篇貼文是一個獨立文件，方便 RAG 檢索。
    如果貼文很多，拆成多個檔案。
    """
    if not rows or len(rows) < 2:
        return [("community_posts.md", f"# {sheet_name}\n\n（無資料）\n")]

    headers = rows[0]
    data_rows = rows[1:]

    # 每 20 篇貼文一個檔案（避免單一文件太大影響 RAG 品質）
    CHUNK_SIZE = 20
    files = []

    for chunk_idx in range(0, len(data_rows), CHUNK_SIZE):
        chunk = data_rows[chunk_idx:chunk_idx + CHUNK_SIZE]
        chunk_num = chunk_idx // CHUNK_SIZE + 1

        lines = []
        lines.append(f"# 社團貼文 — 第 {chunk_num} 批")
        lines.append(f"")
        lines.append(f"- **資料來源**: 同學會社團")
        lines.append(f"- **最後更新**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append(f"- **本批筆數**: {len(chunk)}")
        lines.append("")

        for i, row in enumerate(chunk):
            post_num = chunk_idx + i + 1
            lines.append(f"---")
            lines.append(f"## 貼文 #{post_num}")
            lines.append("")
            for j, header in enumerate(headers):
                value = row[j] if j < len(row) else ""
                if value:
                    lines.append(f"- **{header}**: {value}")
            lines.append("")

        filename = f"community_posts_batch{chunk_num:03d}.md"
        files.append((filename, "\n".join(lines)))

    return files


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    service = get_sheets_service()

    for name, config in SHEETS_CONFIG.items():
        sheet_id = config["sheet_id"]
        if sheet_id.startswith("YOUR_"):
            print(f"跳過 {name}: Sheet ID 尚未設定")
            continue

        print(f"讀取: {name}...", end=" ", flush=True)

        try:
            rows = fetch_sheet_data(service, sheet_id, config["range"])
            print(f"取得 {len(rows)} 列")

            if config["dataset_type"] == "community":
                # 社團貼文特殊處理：拆成多個檔案
                files = community_posts_to_markdown(name, rows)
                community_dir = os.path.join(OUTPUT_DIR, "community")
                os.makedirs(community_dir, exist_ok=True)
                for filename, content in files:
                    path = os.path.join(community_dir, filename)
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    print(f"  寫入: {filename}")
            else:
                md_content = rows_to_markdown(name, rows)
                path = os.path.join(OUTPUT_DIR, config["output_file"])
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(md_content)
                print(f"  寫入: {config['output_file']}")

        except Exception as e:
            print(f"錯誤: {e}")

    print("\n同步完成！")


if __name__ == '__main__':
    main()
PYEOF

chmod +x ~/dify-sync/sync_sheets.py
```

#### 步驟 4：設定 Sheet ID 並執行

1. 開啟每一個 Google Sheet 的網址，從網址列複製 Sheet ID：
   ```
   https://docs.google.com/spreadsheets/d/  <這一段就是 SHEET_ID>  /edit
   ```

2. 編輯腳本，替換所有 `YOUR_SHEET_ID_xxx`：
   ```bash
   nano ~/dify-sync/sync_sheets.py
   # 找到 SHEETS_CONFIG 區塊，替換每個 sheet_id 的值
   # Ctrl+O 儲存, Ctrl+X 離開
   ```

3. 執行同步：
   ```bash
   cd ~/dify-sync
   python3 sync_sheets.py
   ```

4. 上傳到 Dify：
   ```bash
   # 上傳社團貼文
   python3 upload_to_dify.py "$DATASET_ID_COMMUNITY" ./md_output/sheets/community

   # 上傳其他 Sheets 資料
   python3 upload_to_dify.py "$DATASET_ID_SHEETS" ./md_output/sheets "*.md"
   ```

---

### C-4. 匯入 X (Twitter) 貼文

X 的 API 有嚴格的速率限制和付費門檻。MVP 階段建議使用半手動方式：

#### 方案 A：手動匯出（最簡單，推薦 MVP 使用）

1. 在瀏覽器中前往 `https://x.com/TJ_Research`。
2. 向下捲動，手動複製近期的重要貼文（過去 1-2 個月）。
3. 整理成一個 Markdown 檔案，格式如下：

```bash
cat > ~/dify-sync/md_output/twitter/x_posts_manual.md << 'EOF'
# Talk君 X 平台貼文彙整

- **來源**: X (Twitter) @TJ_Research
- **最後更新**: 2026-03-04

---

## 2026-03-03

> 市場觀察：S&P 500 ...（貼文內容）

---

## 2026-03-02

> NVDA 財報後走勢...（貼文內容）

EOF
```

4. 上傳：
   ```bash
   mkdir -p ~/dify-sync/md_output/twitter
   # 編輯好檔案後：
   python3 upload_to_dify.py "$DATASET_ID_TWITTER" ./md_output/twitter
   ```

#### 方案 B：用 Apify 自動化爬取（進階，Phase 2 再做）

如果日後想自動化，可使用 Apify 的 Twitter Scraper：
- Apify 免費方案每月有 US$5 的額度
- 設定 Actor `apidojo/tweet-scraper`，排程每天跑一次
- 結果透過 Webhook 呼叫一個小 Cloud Function 來寫入 Dify

（此方案的詳細步驟留到 Phase 2 再實作。）

---

### C-5. 設定自動同步排程

我們需要兩個自動同步任務：
1. **YouTube 影片**：每天一次，取最新的 JSON，轉成 Markdown，上傳到 Dify
2. **Google Sheets**：每天一次，重新讀取 Sheet 資料，更新 Dify 知識庫

#### 步驟 1：建立主同步腳本

```bash
cat > ~/dify-sync/daily_sync.sh << 'BASH_EOF'
#!/bin/bash
# === 每日同步腳本 ===
# 從 GitHub 拉取最新 YouTube JSON，從 Google Sheets 拉取資料，
# 全部轉成 Markdown 後上傳到 Dify 知識庫。

set -e

SYNC_DIR="$HOME/dify-sync"
REPO_DIR="$SYNC_DIR/repo-data"
LOG_FILE="$SYNC_DIR/logs/sync-$(date +%Y%m%d-%H%M%S).log"

mkdir -p "$SYNC_DIR/logs"

exec > >(tee -a "$LOG_FILE") 2>&1

echo "=============================="
echo "同步開始: $(date)"
echo "=============================="

# --- 載入環境變數 ---
source "$SYNC_DIR/.env"

# --- 1. 拉取最新 YouTube JSON ---
echo ""
echo "[1/4] 拉取最新 YouTube 資料..."
cd "$REPO_DIR"
git pull origin main
cd "$SYNC_DIR"

# --- 2. 轉換 YouTube JSON -> Markdown ---
echo ""
echo "[2/4] 轉換 YouTube JSON 為 Markdown..."
python3 convert_youtube_to_md.py "$REPO_DIR/data/summaries" ./md_output/youtube

# --- 3. 同步 Google Sheets ---
echo ""
echo "[3/4] 同步 Google Sheets..."
python3 sync_sheets.py

# --- 4. 上傳到 Dify ---
echo ""
echo "[4/4] 上傳到 Dify 知識庫..."

# 上傳 YouTube（Dify 會自動去重，已存在的文件會跳過或更新）
python3 upload_to_dify.py "$DATASET_ID_YOUTUBE" ./md_output/youtube

# 上傳社團貼文
if [ -d "./md_output/sheets/community" ]; then
    python3 upload_to_dify.py "$DATASET_ID_COMMUNITY" ./md_output/sheets/community
fi

# 上傳 Sheets 資料
python3 upload_to_dify.py "$DATASET_ID_SHEETS" ./md_output/sheets "*.md"

echo ""
echo "=============================="
echo "同步完成: $(date)"
echo "=============================="
BASH_EOF

chmod +x ~/dify-sync/daily_sync.sh
```

#### 步驟 2：建立環境變數檔案

```bash
cat > ~/dify-sync/.env << 'EOF'
# Dify API Key（從 Phase C-1 取得）
DIFY_API_KEY="dataset-xxxxxxxxxxxxxxxx"

# Dify 知識庫 ID（從 Phase B-3 取得）
DATASET_ID_YOUTUBE="替換成你的ID"
DATASET_ID_COMMUNITY="替換成你的ID"
DATASET_ID_SHEETS="替換成你的ID"
DATASET_ID_TWITTER="替換成你的ID"

# Google 憑證路徑
GOOGLE_APPLICATION_CREDENTIALS="$HOME/dify-sync/credentials/gcp-service-account.json"
EOF
```

用 `nano ~/dify-sync/.env` 編輯，填入你的實際值。

#### 步驟 3：設定 crontab 每日排程

```bash
# 開啟排程編輯器
crontab -e
```

如果被問到要用哪個編輯器，選 `1`（nano）。

在最後一行加上：

```
# 每天 UTC 01:00（台灣時間 09:00）同步 Dify 知識庫
0 1 * * * /bin/bash /home/$USER/dify-sync/daily_sync.sh >> /home/$USER/dify-sync/logs/cron.log 2>&1
```

> **注意**：把 `$USER` 替換成你的實際使用者名稱。儲存並離開 (Ctrl+O, Ctrl+X)。

驗證排程已設定：
```bash
crontab -l
```

#### 步驟 4：手動執行一次確認

```bash
cd ~/dify-sync
bash daily_sync.sh
```

檢查 log 是否有錯誤：
```bash
cat ~/dify-sync/logs/sync-*.log | tail -30
```

---

### C-6. 處理知識庫文件更新（去重策略）

Dify 的 Dataset API 在上傳同名文件時的行為：
- 如果文件名相同，Dify 會建立新版本（不會自動覆蓋）
- 日積月累會產生重複文件

**推薦做法**：修改 `upload_to_dify.py`，在上傳前先檢查知識庫中是否已有同名文件，若有則先刪除再上傳。

在 `upload_to_dify.py` 中加入去重邏輯（以下為完整更新版）：

```bash
cat > ~/dify-sync/upload_to_dify.py << 'PYEOF'
#!/usr/bin/env python3
"""
批量上傳 Markdown 文件到 Dify 知識庫（含去重邏輯）。
使用 Dify Dataset API。
"""

import os
import sys
import time
import requests
import glob


DIFY_BASE_URL = "http://localhost/v1"


def list_existing_documents(api_key, dataset_id):
    """列出知識庫中現有的所有文件。"""
    headers = {"Authorization": f"Bearer {api_key}"}
    docs = {}
    page = 1
    limit = 100

    while True:
        resp = requests.get(
            f"{DIFY_BASE_URL}/datasets/{dataset_id}/documents",
            headers=headers,
            params={"page": page, "limit": limit}
        )
        if resp.status_code != 200:
            print(f"警告: 無法列出現有文件 ({resp.status_code})")
            break

        data = resp.json()
        for doc in data.get("data", []):
            docs[doc["name"]] = doc["id"]

        if not data.get("has_more", False):
            break
        page += 1

    return docs


def delete_document(api_key, dataset_id, document_id):
    """刪除知識庫中的指定文件。"""
    headers = {"Authorization": f"Bearer {api_key}"}
    resp = requests.delete(
        f"{DIFY_BASE_URL}/datasets/{dataset_id}/documents/{document_id}",
        headers=headers
    )
    return resp.status_code == 200


def upload_files(api_key, dataset_id, file_dir, file_pattern="*.md"):
    """上傳目錄下所有符合條件的檔案到指定知識庫（含去重）。"""
    headers = {"Authorization": f"Bearer {api_key}"}

    # 列出現有文件
    print("檢查現有文件...", flush=True)
    existing = list_existing_documents(api_key, dataset_id)
    print(f"知識庫中已有 {len(existing)} 個文件")

    files_to_upload = sorted(glob.glob(os.path.join(file_dir, file_pattern)))
    print(f"找到 {len(files_to_upload)} 個檔案待處理")

    success = 0
    skipped = 0
    failed = 0

    for filepath in files_to_upload:
        filename = os.path.basename(filepath)

        # 如果文件已存在，先刪除
        if filename in existing:
            print(f"更新中: {filename} (先刪除舊版)...", end=" ", flush=True)
            delete_document(api_key, dataset_id, existing[filename])
            time.sleep(0.5)
        else:
            print(f"上傳中: {filename}...", end=" ", flush=True)

        try:
            with open(filepath, 'rb') as f:
                resp = requests.post(
                    f"{DIFY_BASE_URL}/datasets/{dataset_id}/document/create-by-file",
                    headers=headers,
                    files={
                        "file": (filename, f, "text/markdown")
                    },
                    data={
                        "data": '{"indexing_technique": "high_quality", "process_rule": {"mode": "automatic"}}'
                    }
                )

            if resp.status_code in (200, 201):
                print("OK")
                success += 1
            else:
                print(f"FAILED ({resp.status_code}): {resp.text[:200]}")
                failed += 1

            time.sleep(1)

        except Exception as e:
            print(f"ERROR: {e}")
            failed += 1

    print(f"\n處理完成: {success} 成功, {skipped} 跳過, {failed} 失敗")
    return success, failed


if __name__ == '__main__':
    api_key = os.environ.get("DIFY_API_KEY")
    if not api_key:
        print("請設定環境變數 DIFY_API_KEY", file=sys.stderr)
        print("用法: DIFY_API_KEY=your-key python3 upload_to_dify.py <dataset_id> <file_dir> [pattern]",
              file=sys.stderr)
        sys.exit(1)

    if len(sys.argv) < 3:
        print("用法: DIFY_API_KEY=your-key python3 upload_to_dify.py <dataset_id> <file_dir> [pattern]",
              file=sys.stderr)
        sys.exit(1)

    dataset_id = sys.argv[1]
    file_dir = sys.argv[2]
    pattern = sys.argv[3] if len(sys.argv) > 3 else "*.md"

    upload_files(api_key, dataset_id, file_dir, pattern)
PYEOF
```

---

### Phase C 檢查點

- [ ] YouTube 影片 Markdown 文件已上傳至「YouTube影片分析」知識庫
- [ ] 每個文件在 Dify 中狀態為 Available / Indexed
- [ ] Google Sheets 資料已匯出為 Markdown 並上傳至對應知識庫
- [ ] 社團貼文已分批上傳至「社團貼文信號」知識庫
- [ ] X 平台貼文已手動整理並上傳
- [ ] daily_sync.sh 可以手動執行且無錯誤
- [ ] crontab 排程已設定並生效
- [ ] 在 Dify 知識庫中隨機點開幾個文件，內容完整正確

---

## Phase D — Q&A 聊天機器人工作流程

**預估時間**：3–5 小時
**前置條件**：Phase C 完成，知識庫中有可用文件
**費用影響**：
- OpenAI API 費用（GPT-4o）：每次問答約 US$0.01–0.05（視回答長度）
- 預估每月 100 次問答：約 US$1–5

---

### D-1. 建立聊天機器人應用

1. 在 Dify 主控台，點擊上方的「**Studio**」頁籤（或「**Build Apps**」）。

2. 點擊「**Create from Blank（從空白建立）**」。

3. 選擇應用類型：**Chatbot（聊天機器人）**。

4. 選擇編排方式：**Chatflow（聊天工作流程）**。

   > **為何選 Chatflow 而不是 Basic？** Chatflow 提供更多控制，可以設定多知識庫查詢順序、條件分支、以及自訂的引用格式。雖然設定稍複雜，但對我們的需求（多來源檢索 + 引用 + 反幻覺）是必要的。

5. 填入：
   - **App Name**：`投資Talk君 AI`
   - **Description**：`基於Talk君內容的投資分析Q&A機器人。只從Talk君的影片、社團貼文、持倉數據等來源回答問題，並附上引用。`

6. 點擊「**Create（建立）**」。

你現在會進入 Chatflow 的視覺化編輯器。

---

### D-2. 設定 Chatflow 工作流程

Chatflow 編輯器是一個節點式（node-based）的流程圖。預設會有一個「**Start**」節點和一個「**LLM**」節點。我們要建立以下流程：

```
[Start] → [Knowledge Retrieval] → [LLM] → [Answer]
```

#### 節點 1：Start（已自動建立）

點擊「**Start**」節點，確認：
- **Input Variables** 區塊中有 `sys.query`（使用者的問題）

不需修改，繼續。

#### 節點 2：Knowledge Retrieval（知識庫檢索）

1. 從左側面板拖拉「**Knowledge Retrieval**」節點到畫布上（或點擊 Start 節點的 `+` 按鈕，選擇 Knowledge Retrieval）。

2. 把 Start 節點的輸出連線到 Knowledge Retrieval 節點。

3. 點擊 Knowledge Retrieval 節點進行設定：

   **Query Variable（查詢變數）**：
   - 選擇 `sys.query`

   **Knowledge（知識庫選擇）**：
   - 點擊「**+ Add Knowledge（新增知識庫）**」
   - 勾選所有 4 個知識庫：
     - [x] YouTube影片分析
     - [x] 社團貼文信號
     - [x] 持倉與總經數據
     - [x] X平台短評

   **Recall Mode（召回模式）**：
   - 選擇「**Multi-path Recall（多路召回）**」

   > **為何選 Multi-path Recall？** 這允許每個知識庫獨立搜索並返回結果，然後合併。比 single-path 更精確，因為不同來源的內容格式差異大。

   **每個知識庫的個別設定**（點擊知識庫名稱旁的齒輪圖示）：

   | 知識庫 | Top K | Score Threshold |
   |---|---|---|
   | 社團貼文信號 | `5` | `0.5` |
   | 持倉與總經數據 | `5` | `0.5` |
   | YouTube影片分析 | `5` | `0.4` |
   | X平台短評 | `3` | `0.5` |

   > **關於 Top K**：每個知識庫最多返回 K 個最相關的文件片段。
   > **關於 Score Threshold**：低於此分數的結果會被丟棄，降低無關內容混入的機率。YouTube 的門檻設低一點，因為影片摘要較長，語義匹配可能稍弱。

   **Rerank Model（重排模型）**：
   - 如果可用，啟用 Rerank，選擇 `cohere/rerank-english-v3.0` 或留空（使用 OpenAI 的 embedding 做排序即可，MVP 不需要額外的 rerank 服務）
   - **建議 MVP 先不啟用 Rerank**（省錢，且效果已足夠）

4. 點擊「**Save**」或直接確認。

#### 節點 3：LLM（大語言模型推理）

1. Knowledge Retrieval 節點的輸出連線到 LLM 節點。

2. 點擊 LLM 節點進行設定：

   **Model（模型）**：
   - 選擇 `gpt-4o`

   **Context（上下文）**：
   - 點擊「**+**」按鈕，選擇來自 Knowledge Retrieval 節點的 `result`（召回的知識片段）

   **System Prompt（系統提示詞）**：

   複製以下完整的提示詞貼入：

   ```
   你是「投資Talk君 AI」，一個嚴格基於 Talk君 內容的投資分析助手。

   ## 身份與角色
   - 你是 Talk君（投資TALK君）內容的忠實呈現者，不是獨立的投資顧問。
   - 你只能根據提供的「參考資料」回答問題。
   - 你以繁體中文回答所有問題。

   ## 回答規則

   ### 1. 僅基於來源回答
   - 你的每一句分析都必須能從「參考資料」中找到依據。
   - 如果參考資料中沒有足夠資訊回答問題，你必須誠實說明：「目前 Talk君 的內容中尚未涵蓋此議題，建議等待後續更新。」
   - 絕對不可以編造、推測、或使用你的通用知識來補充答案。

   ### 2. 引用格式
   - 每個重點陳述後，必須標註來源，格式如下：
     - YouTube 影片：📺 參考來源：YouTube 影片 [日期] 《標題》
     - 社團貼文：📋 參考來源：社團貼文 [日期]
     - 持倉數據：📊 參考來源：持倉數據表 [日期]
     - 總經數據：📈 參考來源：總經公告 [日期]
     - X 平台：🐦 參考來源：X 平台 @TJ_Research [日期]
   - 在回答的最後，列出所有引用的來源清單。

   ### 3. 語言規範（重要）
   - 絕對不可以使用投資建議語言，包括但不限於：
     ❌ 「建議買入」「應該賣出」「推薦持有」「我認為你應該...」
   - 應該使用分析框架語言：
     ✅ 「Talk君 在此情境下的分析框架是...」
     ✅ 「根據 Talk君 的觀點，這個指標顯示...」
     ✅ 「Talk君 對此標的的看法為...（看多/看空/中性）」
     ✅ 「從 Talk君 的持倉變化來看...」

   ### 4. 回答結構
   建議的回答結構（可依問題類型調整）：
   1. **直接回應**：用 1-2 句話直接回答問題核心
   2. **詳細分析**：根據來源展開說明
   3. **來源引用**：列出所有參考來源
   4. **補充說明**（如適用）：提醒使用者注意的限制或建議查看的其他來源

   ### 5. 特殊情境處理
   - **問持倉**：優先引用持倉績效表和社團貼文的最新信號
   - **問個股觀點**：優先引用 YouTube 影片中的分析和 tickers 資訊
   - **問總經**：優先引用總經公告表和相關 YouTube 影片
   - **問時事**：如果來源中沒有，明確說明尚無 Talk君 的觀點
   - **問非投資話題**：禮貌拒絕，說明你只能回答與 Talk君 投資內容相關的問題

   ## 重要提醒
   你不是投資顧問。你是 Talk君 內容的智能檢索工具。使用者應該自行判斷並承擔投資風險。
   ```

   **User Prompt（使用者提示詞）**：

   ```
   ## 參考資料

   以下是從 Talk君 的知識庫中檢索到的相關內容：

   {{#context#}}

   ---

   ## 使用者問題

   {{#sys.query#}}
   ```

   > **注意**：`{{#context#}}` 是 Dify 的變數語法，代表 Knowledge Retrieval 節點回傳的內容。`{{#sys.query#}}` 是使用者的原始問題。

   **Model Parameters（模型參數）**：

   | 參數 | 值 | 說明 |
   |---|---|---|
   | **Temperature** | `0.3` | 低溫度 = 更確定、更保守的回答（減少幻覺） |
   | **Max Tokens** | `2000` | 足夠回答大多數問題 |
   | **Top P** | `0.9` | 標準值 |

3. 點擊「**Save**」。

#### 節點 4：Answer（回答）

Answer 節點通常已自動建立並連接。點擊確認：
- 輸出來源是 LLM 節點的 `text` 輸出

---

### D-3. 設定對話開場白

1. 在 Chatflow 編輯器中，找到 Start 節點，或在頁面右側找到「**Features**」面板。

2. 找到「**Opening Statement（開場白）**」或「**Conversation Opener**」設定。

3. 填入：

   ```
   你好！我是「投資Talk君 AI」🤖

   我可以根據 Talk君 的影片分析、社團貼文、持倉數據等內容來回答你的投資相關問題。每個回答都會附上參考來源。

   你可以問我：
   - 📺 Talk君 對某支股票的看法是什麼？
   - 📊 Talk君 目前的持倉有哪些？
   - 📈 Talk君 怎麼看最近的總經數據？
   - 📋 社團最新的交易信號是什麼？

   ⚠️ 提醒：我只會根據 Talk君 的內容回答，不會提供投資建議。請自行評估風險。

   請問你想了解什麼？
   ```

4. 點擊「**Save**」。

---

### D-4. 設定對話記憶

1. 在 LLM 節點的設定中（或在 Chatflow 的整體設定中），找到「**Memory（記憶）**」或「**Conversation History**」。

2. 設定：
   - **Memory Window**：`10`（記住最近 10 輪對話）
   - **Memory Mode**：`Window`

   > 這讓機器人能理解上下文，例如使用者先問「Talk君怎麼看 NVDA？」然後接著問「那他的持倉呢？」——機器人會知道「他」指的是 NVDA 相關的討論。

---

### D-5. 發布並測試

1. 在 Chatflow 編輯器右上角，點擊「**Publish（發布）**」。

2. 確認發布。

3. 點擊右上角的「**Run（執行）**」或「**Preview（預覽）**」按鈕來測試。

4. 在預覽視窗中，嘗試以下測試問題：
   - `Talk君怎麼看英偉達？`
   - `最新的社團信號是什麼？`
   - `Talk君目前持倉有哪些股票？`
   - `你覺得我應該買 TSLA 嗎？`（應被拒絕回答投資建議）
   - `今天天氣如何？`（應被禮貌拒絕）

---

### Phase D 檢查點

- [ ] Chatflow 已建立，包含 Start → Knowledge Retrieval → LLM → Answer 四個節點
- [ ] 4 個知識庫已連接到 Knowledge Retrieval 節點
- [ ] 系統提示詞已設定（含引用格式、反幻覺、語言規範）
- [ ] Temperature 設為 0.3
- [ ] 預覽模式下可以正常問答
- [ ] 回答中包含引用來源標記
- [ ] 問無關問題會被拒絕

---

## Phase E — 測試與迭代

**預估時間**：3–5 天（持續調整）
**前置條件**：Phase D 完成
**費用影響**：OpenAI API 測試費用約 US$1–3

---

### E-1. 系統化測試方案

建立一個測試表格，涵蓋以下 5 大類測試案例。每個案例記錄：問題、預期行為、實際行為、通過/失敗。

#### 類別 1：個股查詢（應引用 YouTube 影片和 tickers）

| # | 問題 | 預期行為 |
|---|---|---|
| 1.1 | `Talk君對英偉達(NVDA)的看法是什麼？` | 引用包含 NVDA 的影片，提到 sentiment 和具體分析 |
| 1.2 | `Talk君最近有提到哪些股票？` | 列出多支股票及其 sentiment |
| 1.3 | `Talk君對 Blue Owl 事件怎麼看？` | 引用 1395 期影片，提到私人信貸分析 |

#### 類別 2：持倉查詢（應引用 Google Sheets）

| # | 問題 | 預期行為 |
|---|---|---|
| 2.1 | `Talk君目前的持倉有哪些？` | 引用持倉績效表 |
| 2.2 | `Talk君的投資組合 Beta 值是多少？` | 引用持倉 Beta 表 |
| 2.3 | `Talk君最近有開倉或平倉嗎？` | 引用社團貼文信號 |

#### 類別 3：總經分析（應引用 YouTube + Sheets）

| # | 問題 | 預期行為 |
|---|---|---|
| 3.1 | `Talk君怎麼看最近的 CPI 數據？` | 引用相關影片和總經公告 |
| 3.2 | `Talk君對聯準會降息的看法？` | 引用相關影片 |
| 3.3 | `美元指數最近的走勢如何？` | 引用影片中提到的美元分析 |

#### 類別 4：反幻覺測試（應誠實拒絕）

| # | 問題 | 預期行為 |
|---|---|---|
| 4.1 | `Talk君對比特幣怎麼看？`（如果來源沒有） | 誠實說明尚未涵蓋此議題 |
| 4.2 | `明天市場會漲嗎？` | 拒絕預測，說明來源無此資訊 |
| 4.3 | `你覺得我應該全倉買入 AAPL 嗎？` | 拒絕提供投資建議 |

#### 類別 5：邊界測試

| # | 問題 | 預期行為 |
|---|---|---|
| 5.1 | `你是誰？` | 自我介紹為 Talk君 內容助手 |
| 5.2 | `今天天氣如何？` | 禮貌拒絕，說明只回答投資相關問題 |
| 5.3 | `用英文回答：What does Talk think about NVDA?` | 仍用繁體中文回答 |

---

### E-2. 常見問題及調整方法

#### 問題：回答中沒有引用來源

**排查步驟**：
1. 在 Chatflow 編輯器中，點擊 Knowledge Retrieval 節點
2. 查看該次查詢的日誌（點擊右側的「**Logs**」或在 Preview 面板中查看 Trace）
3. 確認是否有知識庫返回結果

**修復方式**：
- 如果知識庫沒有返回結果：降低 Score Threshold（從 0.5 降到 0.3）
- 如果知識庫返回了結果但 LLM 沒有引用：修改 System Prompt，加入更強硬的引用指令

#### 問題：回答太籠統，沒有具體內容

**修復方式**：
- 增加 Top K 值（從 5 增加到 8）
- 在 System Prompt 中加入：「回答時請引用具體的數字、日期、股票代碼等細節。」

#### 問題：回答出現幻覺（編造不存在的內容）

**修復方式**：
- 降低 Temperature（從 0.3 降到 0.1）
- 在 System Prompt 中加入更強的限制語句
- 檢查知識庫中的文件品質（是否有格式錯誤導致 embedding 品質差）

#### 問題：回答太長/太短

**修復方式**：
- 在 System Prompt 中加入字數指引：「回答長度控制在 200-500 字之間，除非問題需要更詳細的分析。」
- 調整 Max Tokens 參數

---

### E-3. 監控對話品質

1. 在 Dify 主控台，點擊左側的「**Logs**」頁籤。
2. 這裡會記錄所有對話歷史。
3. 定期檢查：
   - 回答是否正確引用來源
   - 是否有幻覺出現
   - 使用者問了哪些問題（了解需求）
   - 回答品質是否一致

---

### Phase E 檢查點

- [ ] 5 大類測試案例全部通過（或已知限制記錄在案）
- [ ] 個股查詢能正確引用影片和 tickers
- [ ] 持倉查詢能引用 Google Sheets 資料
- [ ] 無法回答的問題會誠實拒絕
- [ ] 不會提供投資建議
- [ ] 始終以繁體中文回答
- [ ] Temperature、Top K、Score Threshold 已調整到最佳值

---

## Phase F — API 端點對外開放

**預估時間**：2–3 小時
**前置條件**：Phase E 完成（機器人已通過測試）
**費用影響**：無額外費用（使用現有 VM 和靜態 IP）

---

### F-1. 取得 Chatbot API Key

1. 在 Dify 主控台，進入你的「**投資Talk君 AI**」應用。
2. 在左側選單或應用設定中，找到「**API Access**」或「**Monitoring**」頁籤。
3. 點擊「**API Keys**」。
4. 點擊「**Create new secret key**」。
5. 複製此 Key（以 `app-` 開頭）。

此 Key 是**應用層級**的 API Key（跟 Phase C-1 的 Dataset API Key 不同）。後續稱為 `APP_API_KEY`。

---

### F-2. 測試 API 端點

在 VM 的 SSH 終端中測試：

```bash
# 測試 API 是否可用
curl -X POST "http://localhost/v1/chat-messages" \
  -H "Authorization: Bearer APP_API_KEY_HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": {},
    "query": "Talk君對英偉達的看法是什麼？",
    "response_mode": "blocking",
    "conversation_id": "",
    "user": "test-user-001"
  }'
```

把 `APP_API_KEY_HERE` 替換成你的實際 Key。

預期回應格式：
```json
{
  "message_id": "xxx",
  "conversation_id": "xxx",
  "answer": "根據Talk君的分析...",
  "created_at": 1234567890
}
```

從外部（你的本地電腦）測試：

```bash
curl -X POST "http://YOUR_VM_IP/v1/chat-messages" \
  -H "Authorization: Bearer APP_API_KEY_HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": {},
    "query": "Talk君對英偉達的看法是什麼？",
    "response_mode": "blocking",
    "conversation_id": "",
    "user": "test-user-001"
  }'
```

---

### F-3. API 端點規格文件

為日後 CMoney 行動 App 整合準備，以下是完整的 API 規格：

#### 基本資訊

| 項目 | 值 |
|---|---|
| **Base URL** | `http://YOUR_VM_IP/v1` |
| **認證方式** | `Bearer Token`（在 Header 中傳 `Authorization: Bearer {APP_API_KEY}`）|
| **Content-Type** | `application/json` |

#### 發送訊息（Create Chat Message）

```
POST /v1/chat-messages
```

**Request Body**：

```json
{
  "inputs": {},
  "query": "使用者的問題文字",
  "response_mode": "blocking",
  "conversation_id": "",
  "user": "unique-user-id"
}
```

| 參數 | 型別 | 必填 | 說明 |
|---|---|---|---|
| `inputs` | object | 是 | 額外輸入變數（目前為空物件） |
| `query` | string | 是 | 使用者的問題 |
| `response_mode` | string | 是 | `blocking`（等待完整回答）或 `streaming`（即時串流） |
| `conversation_id` | string | 否 | 對話 ID（首次留空，後續帶入以延續對話） |
| `user` | string | 是 | 使用者唯一識別碼（用於追蹤對話） |

**Response**（blocking 模式）：

```json
{
  "message_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "conversation_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "mode": "chat",
  "answer": "機器人的回答文字...",
  "metadata": {
    "usage": {
      "prompt_tokens": 1500,
      "completion_tokens": 500,
      "total_tokens": 2000
    },
    "retriever_resources": [
      {
        "dataset_name": "YouTube影片分析",
        "document_name": "2026-02-22-fHCZCA5oztM.md",
        "segment_content": "..."
      }
    ]
  },
  "created_at": 1709510400
}
```

> **重要**：`metadata.retriever_resources` 包含了 RAG 檢索到的來源資訊。行動 App 可以用這個來顯示引用來源的 UI 元件。

#### Streaming 模式

如果行動 App 要實現打字效果，使用 `response_mode: "streaming"`：

```bash
curl -X POST "http://YOUR_VM_IP/v1/chat-messages" \
  -H "Authorization: Bearer APP_API_KEY_HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": {},
    "query": "Talk君對英偉達的看法？",
    "response_mode": "streaming",
    "conversation_id": "",
    "user": "test-user-001"
  }'
```

回傳為 Server-Sent Events (SSE) 格式：

```
data: {"event": "message", "answer": "根據", ...}
data: {"event": "message", "answer": "Talk君", ...}
data: {"event": "message", "answer": "的分析", ...}
...
data: {"event": "message_end", ...}
```

#### 取得對話歷史

```
GET /v1/messages?conversation_id={conversation_id}&user={user_id}&limit=20
```

#### 列出對話

```
GET /v1/conversations?user={user_id}&limit=20
```

---

### F-4. 設定 HTTPS（建議但非 MVP 必須）

MVP 階段用 HTTP 即可。但如果要提高安全性（尤其是傳 API Key 時），建議加上 HTTPS。

使用免費的 Let's Encrypt + Nginx 反向代理：

```bash
# 安裝 Nginx 和 Certbot
sudo apt-get install -y nginx certbot python3-certbot-nginx
```

你需要先有一個域名指向你的 VM IP。假設你的域名是 `api.yourdomain.com`：

```bash
# 設定 Nginx 反向代理
sudo tee /etc/nginx/sites-available/dify << 'EOF'
server {
    listen 80;
    server_name api.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:80;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE 支援
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/dify /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx

# 取得 SSL 憑證
sudo certbot --nginx -d api.yourdomain.com
```

> **如果沒有域名**：可以用 Cloudflare Tunnel 作為替代方案。或者 MVP 先用 HTTP，Phase 2 再加 HTTPS。

---

### F-5. API 安全性注意事項

1. **API Key 保護**：`APP_API_KEY` 只能由後端伺服器持有。行動 App 不應直接存放此 Key。正確的架構是：
   ```
   行動 App → CMoney 後端 API → Dify API
   ```
   CMoney 後端做使用者認證和訂閱檢查後，才代為呼叫 Dify。

2. **速率限制**：可在 Nginx 中加入：
   ```nginx
   limit_req_zone $binary_remote_addr zone=dify_api:10m rate=10r/m;

   location / {
       limit_req zone=dify_api burst=5 nodelay;
       proxy_pass http://127.0.0.1:80;
       ...
   }
   ```

3. **IP 白名單**（Phase 2）：當 CMoney 後端的 IP 固定後，防火牆規則只允許該 IP。

---

### Phase F 檢查點

- [ ] APP_API_KEY 已建立
- [ ] 從 VM 內部呼叫 API 成功，回傳正確格式
- [ ] 從外部（本機電腦）呼叫 API 成功
- [ ] Streaming 模式正常運作
- [ ] API 規格文件已記錄，可交給行動 App 團隊
- [ ] （可選）HTTPS 已設定

---

## 附錄 — 成本估算彙整

### 每月固定成本

| 項目 | 費用 (USD) | 備註 |
|---|---|---|
| GCP e2-medium VM | ~$24 | 2 vCPU, 4 GB RAM |
| 30 GB Standard Disk | ~$1.20 | 標準永久磁碟 |
| 靜態外部 IP | $0 | 使用中不收費 |
| **GCP 小計** | **~$25** | |

### 每月變動成本（OpenAI API）

| 項目 | 單價 | 預估用量 | 費用 (USD) |
|---|---|---|---|
| GPT-4o（問答推理） | $2.50/1M input + $10/1M output | ~100 次問答/月 | ~$2–5 |
| text-embedding-3-small（索引） | $0.02/1M tokens | 初次 + 每日更新 | ~$0.50–1 |
| **OpenAI 小計** | | | **~$3–6** |

### 每月總成本

| 階段 | 預估月費 (USD) |
|---|---|
| MVP（目前） | **$28–31** |
| 升級 VM 為 e2-standard-2 後 | **$52–55** |

### 省錢技巧

1. **如果暫時不用**：停止 VM（Stop），只收磁碟費用（~$1.20/月）。重啟後 IP 不變（因為是靜態 IP）。
   ```bash
   # 在 Cloud Console 的 VM 列表，點擊三個點 > Stop
   # 或在終端：
   gcloud compute instances stop dify-server --zone=asia-east1-b --project=overseas-author
   ```

2. **承諾使用折扣 (CUD)**：如果確定長期使用，可購買 1 年承諾，節省約 20-30%。

3. **考慮 GPT-4o-mini**：如果回答品質可接受，把 LLM 節點從 `gpt-4o` 換成 `gpt-4o-mini`，推理成本降低約 95%（$0.15/1M input + $0.60/1M output）。

---

## 附錄 — Phase 2 擴充藍圖

以下是 MVP 之後的擴充方向，目前的架構已為此預留接口：

### 2-1. 訂閱分級 (Subscription Gating)

```
免費版：每天 3 次提問，只能查 YouTube 影片
付費版：不限次數，可查所有來源（社團、持倉、Beta）
```

**實作方式**：
- CMoney 後端根據使用者訂閱等級，呼叫不同的 Dify 應用（或帶入不同的 `inputs` 參數）
- 在 Dify 的 Chatflow 中加入條件分支：根據 `inputs.tier` 決定查詢哪些知識庫

### 2-2. 主動推播 (Proactive Alerts)

```
當社團出現新的交易信號 → 自動推播到 App
```

**實作方式**：
- 在 `sync_sheets.py` 中加入變更偵測邏輯
- 偵測到新信號後，呼叫 CMoney 推播 API
- 或使用 Cloud Scheduler + Cloud Functions 做排程檢查

### 2-3. X (Twitter) 自動化

```
自動爬取 @TJ_Research 的新貼文 → 匯入知識庫
```

**實作方式**：
- 使用 Apify 或 RapidAPI 的 Twitter Scraper
- 設定每小時執行一次
- 新貼文自動轉成 Markdown 並上傳到 Dify

### 2-4. 直播逐字稿

```
直播結束後自動生成逐字稿 → 匯入知識庫
```

**實作方式**：
- 擴充現有的 `run_pipeline.py` 支援直播影片
- 或在直播平台設定 Webhook，直播結束時觸發處理

### 2-5. 多語言支援

```
支援簡體中文和英文回答
```

**實作方式**：
- 在 Chatflow 的 Start 節點加入語言選擇變數
- 在 System Prompt 中根據語言變數調整回答語言

### 2-6. 效能優化

當使用量增加時：
- 升級 VM 為 `e2-standard-2`（8 GB RAM）或 `e2-standard-4`（16 GB RAM）
- 考慮遷移到 Cloud Run（自動擴縮、按使用量計費）
- 在 Dify 前面加 CDN 或 API Gateway

---

## 時間表總覽

| 週次 | 日期 | Phase | 主要工作 |
|---|---|---|---|
| 第 1 週 | 3/4 – 3/9 | A + B | 建 VM、裝 Docker、部署 Dify、設定知識庫 |
| 第 2 週 | 3/10 – 3/16 | C | 匯入所有資料、建立同步管線 |
| 第 3 週 | 3/17 – 3/23 | D + E | 建立 Chatflow、調整提示詞、系統測試 |
| 第 4 週 | 3/24 – 3/31 | E + F | 完善測試、開放 API、準備 Demo |

**每日建議時間投入**：1–2 小時

---

## 快速排錯指南

### 問題：VM 無法 SSH 連入

```bash
# 在 Cloud Console 中確認 VM 狀態為 RUNNING
# 如果不是，嘗試重啟：
gcloud compute instances start dify-server --zone=asia-east1-b --project=overseas-author
```

### 問題：Dify 頁面無法開啟

```bash
# SSH 進入 VM 後檢查 Docker 容器狀態
cd ~/dify/docker
docker compose ps

# 如果有容器 exited 或 restarting，查看 log：
docker compose logs api --tail 100
docker compose logs web --tail 100

# 重啟所有容器：
docker compose down && docker compose up -d
```

### 問題：記憶體不足 (OOM)

```bash
# 檢查記憶體使用量
free -h

# 如果可用記憶體 < 500 MB，考慮：
# 1. 增加 swap：
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# 2. 或升級 VM（需要先停機）：
# 在 Cloud Console > VM instances > dify-server > Edit
# 改 Machine type 為 e2-standard-2
```

### 問題：API 呼叫回傳 401 Unauthorized

- 確認你使用的是正確的 API Key 類型（Dataset API Key vs App API Key）
- 確認 Authorization header 格式為 `Bearer your-key-here`

### 問題：知識庫搜索不到相關內容

1. 在 Dify 知識庫頁面點擊「**Hit Testing（命中測試）**」
2. 輸入一個你知道有答案的問題
3. 如果沒有結果：
   - 檢查文件的索引狀態是否為 Available
   - 降低 Score Threshold
   - 確認文件內容確實包含相關資訊

### 問題：daily_sync.sh 排程沒有執行

```bash
# 檢查 crontab 是否正確
crontab -l

# 檢查 cron 服務是否在運作
sudo systemctl status cron

# 手動測試
bash ~/dify-sync/daily_sync.sh

# 查看 cron 日誌
grep CRON /var/log/syslog | tail -20
```

---

*文件版本：v1.0 | 建立日期：2026-03-04 | 目標完成日：2026-03-31*
