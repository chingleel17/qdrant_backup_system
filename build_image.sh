#!/bin/bash
# 建立 Qdrant 備份 API Docker 映像並推送到 Google Cloud Artifact Registry

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 載入環境變數
source "$SCRIPT_DIR/../../.env"

# 檢查必要環境變數
if [ -z "$GCP_PROJECT_ID" ]; then
    echo "❌ 錯誤: 請在 .env 檔案中設定 GCP_PROJECT_ID"
    exit 1
fi

# 設定映像檔名稱和標籤
IMAGE_NAME="qdrant-backup-api"
IMAGE_TAG=${1:-latest}
REGISTRY_URL="asia-east1-docker.pkg.dev"
FULL_IMAGE_NAME="$REGISTRY_URL/$GCP_PROJECT_ID/qdrant/$IMAGE_NAME:$IMAGE_TAG"

echo "🔧 正在建立 Qdrant 備份 API Docker 映像..."
echo "專案 ID: $GCP_PROJECT_ID"
echo "映像檔名稱: $FULL_IMAGE_NAME"

# 建立映像檔
echo "📦 建構 Docker 映像檔..."
docker build -t $FULL_IMAGE_NAME .

if [ $? -ne 0 ]; then
    echo "❌ Docker 映像檔建構失敗！"
    exit 1
fi

echo "✅ Docker 映像檔建構成功"

# 登入 Artifact Registry
echo "🔐 登入 Google Cloud Artifact Registry..."
gcloud auth print-access-token | \
  docker login -u oauth2accesstoken --password-stdin https://$REGISTRY_URL

if [ $? -ne 0 ]; then
    echo "❌ Artifact Registry 登入失敗！"
    exit 1
fi

# 推送到 Artifact Registry
echo "📤 推送映像檔到 Artifact Registry..."
docker push $FULL_IMAGE_NAME

if [ $? -eq 0 ]; then
    echo "✅ 映像檔推送成功！"
    echo "映像檔位置: $FULL_IMAGE_NAME"

    # 顯示如何使用這個映像檔
    echo ""
    echo "📋 使用方式："
    echo "docker pull $FULL_IMAGE_NAME"
    echo "docker run -d -p 8081:8080 --env-file .env $FULL_IMAGE_NAME"

    # 更新 docker-compose.yml 使用 registry 映像檔的說明
    echo ""
    echo "💡 要在 docker-compose.yml 中使用此映像檔，請將 build 部分替換為："
    echo "  image: $FULL_IMAGE_NAME"

else
    echo "❌ 映像檔推送失敗！"
    exit 1
fi
