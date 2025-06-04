# Qdrant 自動備份系統

這是一個完整的 Qdrant 自動備份解決方案，使用 Google Cloud Platform 的 Cloud Scheduler、Cloud Function 和 VM 上的 API 服務來定期備份 Qdrant collections 到 Google Cloud Storage。

## 系統架構

```
Cloud Scheduler (每小時)
          ↓
Cloud Function (qdrant-backup-trigger)
          ↓ 呼叫 HTTP API
GCP VM (Docker 容器)
          ↓ 執行 Qdrant Snapshot + 上傳 GCS
Google Cloud Storage (csfiledata.ariel.com.tw/qdrant)
```

## 檔案結構

```
deploy/qdrant-backup-image/
├── app/
│   ├── main.py              # 備份 API 服務主程式
│   └── requirements.txt     # Python 相依套件
├── cloud-function/
│   ├── main.py              # Cloud Function 程式碼
│   ├── requirements.txt     # Cloud Function 相依套件
│   └── deploy.sh            # Cloud Function 部署腳本
├── Dockerfile               # Docker 映像檔建構檔案
├── docker-compose.yml       # Docker Compose 設定 (本地建構)
├── docker-compose.registry.yml # Docker Compose 設定 (使用 Registry 映像檔)
├── build_image.sh           # Docker 映像檔建構和推送腳本
├── .env.example             # 環境變數範例
├── setup-scheduler.sh       # Cloud Scheduler 設定腳本
└── README.md               # 本文件
```

## 建構和推送 Docker 映像檔

如果您想要將映像檔推送到 Google Cloud Artifact Registry 以便在多個 VM 上重複使用：

```bash
# 確保已設定 GCP_PROJECT_ID 環境變數
export GCP_PROJECT_ID="your-project-id"

# 建構並推送映像檔
./build_image.sh

# 使用 registry 映像檔版本的 docker-compose
docker-compose -f docker-compose.registry.yml up -d
```

映像檔將會推送到：
`asia-east1-docker.pkg.dev/PROJECT_ID/qdrant/qdrant-backup-api:latest`

## 部署步驟

### 1. 準備環境變數

複製環境變數範例檔案並填入實際值：

```bash
cd deploy/qdrant-backup-image
cp .env.example .env
```

編輯 `.env` 檔案，設定以下變數：

```bash
# Qdrant 連線設定
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_API_KEY=your_qdrant_api_key_here

# GCS 儲存設定
GCS_BUCKET_NAME=csfiledata.ariel.com.tw
GCS_FOLDER_PREFIX=qdrant

# 本地備份路徑
BACKUP_LOCAL_PATH=/tmp/qdrant_snapshots

# GCP 認證設定
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
GOOGLE_APPLICATION_CREDENTIALS_FILE_PATH=/host/path/to/service-account-key.json
```

### 2. 在 VM 上部署備份 API

#### 方法 1: 使用 Docker Compose (本地建構)

```bash
# 在 VM 上執行
cd deploy/qdrant-backup-image

# 啟動服務
docker-compose up -d

# 檢查服務狀態
docker-compose ps
docker-compose logs qdrant-backup-api
```

#### 方法 2: 使用 Artifact Registry 映像檔

```bash
# 先建立並推送映像檔
./build_image.sh

# 使用 registry 版本啟動
docker-compose -f docker-compose.registry.yml up -d
```

#### 方法 3: 單獨建構和執行

```bash
# 建構 Docker 映像檔
docker build -t qdrant-backup-api .

# 執行容器
docker run -d \
  --name qdrant-backup-api \
  -p 8081:8080 \
  --env-file .env \
  qdrant-backup-api
```

### 3. 驗證備份 API

```bash
# 健康檢查
curl http://VM_IP:8081/health

# 檢查 Qdrant 連線狀態
curl http://VM_IP:8081/status

# 列出所有 collections
curl http://VM_IP:8081/collections

# 手動觸發備份測試
curl -X POST http://VM_IP:8081/backup \
  -H "Content-Type: application/json" \
  -d '{}'
```

### 4. 部署 Cloud Function

設定環境變數並部署：

```bash
# 設定必要環境變數
export GCP_PROJECT_ID="your-project-id"
export VM_BACKUP_API_URL="http://VM_INTERNAL_IP:8081"

# 部署 Cloud Function
cd cloud-function
./deploy.sh
```

### 5. 設定 Cloud Scheduler

```bash
# 設定定時排程
./setup-scheduler.sh
```

### 6. 測試完整流程

```bash
# 手動觸發 Cloud Scheduler
gcloud scheduler jobs run qdrant-backup-hourly \
  --location=asia-east1 \
  --project=your-project-id

# 檢視 Cloud Function 日誌
gcloud logging read "resource.type=cloud_function" \
  --limit=50 \
  --format='table(timestamp,severity,textPayload)' \
  --project=your-project-id
```

## API 端點說明

### VM 備份 API

- `GET /health` - 健康檢查
- `GET /status` - 檢查 Qdrant 連線狀態
- `GET /collections` - 列出所有 collections
- `POST /backup` - 觸發備份
  - 請求體: `{}` (備份所有) 或 `{"collection": "collection_name"}` (備份指定)

### Cloud Function

- 入口點: `trigger_qdrant_backup`
- 觸發方式: HTTP POST
- 請求體: `{}` (備份所有) 或 `{"collection": "collection_name"}` (備份指定)

## 監控和日誌

### 查看 Cloud Function 日誌

```bash
gcloud logging read "resource.type=cloud_function AND resource.labels.function_name=qdrant-backup-trigger" \
  --limit=50 \
  --format='table(timestamp,severity,textPayload)' \
  --project=your-project-id
```

### 查看 Cloud Scheduler 執行狀態

```bash
gcloud scheduler jobs describe qdrant-backup-hourly \
  --location=asia-east1 \
  --project=your-project-id
```

### 檢查 VM 上的備份服務日誌

```bash
docker-compose logs -f qdrant-backup-api
```

## 故障排除

### 1. Cloud Function 無法連線到 VM

- 確認 VM 內部 IP 地址正確
- 檢查 VPC 網路設定和防火牆規則
- 確認 VM 上的 API 服務正在運行

### 2. 備份失敗

- 檢查 Qdrant 服務狀態
- 驗證 GCS 權限設定
- 檢查磁碟空間是否足夠

### 3. 權限問題

- 確認 VM 具有 GCS 寫入權限
- 檢查服務帳戶金鑰設定

## 安全考量

1. **網路安全**: VM 上的備份 API 僅監聽內部網路，不對外公開
2. **認證**: 可在 Cloud Function 中加入認證 token
3. **權限**: 使用最小權限原則設定 GCS 權限
4. **加密**: 備份檔案在 GCS 中預設加密儲存

## 自訂設定

### 修改備份頻率

編輯 Cloud Scheduler 的 cron 表達式：

```bash
# 每 30 分鐘
gcloud scheduler jobs update http qdrant-backup-hourly \
  --schedule='*/30 * * * *' \
  --location=asia-east1

# 每天凌晨 2 點
gcloud scheduler jobs update http qdrant-backup-hourly \
  --schedule='0 2 * * *' \
  --location=asia-east1
```

### 備份保留策略

可在 GCS bucket 上設定生命週期規則來自動清理舊備份。

## 成本估算

- Cloud Function: 每次執行約 $0.0000004
- Cloud Scheduler: 每個作業每月 $0.10
- GCS 儲存: 依實際使用量計算
- VM 網路流量: 內部流量免費
