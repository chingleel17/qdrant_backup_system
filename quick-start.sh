#!/bin/bash

# Qdrant 備份系統快速啟動腳本

set -e

echo "🚀 Qdrant 備份系統快速設定"
echo "================================"

# 檢查必要工具
command -v docker >/dev/null 2>&1 || { echo "❌ 請先安裝 Docker"; exit 1; }
command -v gcloud >/dev/null 2>&1 || { echo "❌ 請先安裝 Google Cloud SDK"; exit 1; }

# 檢查環境變數檔案
if [ ! -f .env ]; then
    echo "📝 建立環境變數檔案..."
    cp .env.example .env
    echo "⚠️  請編輯 .env 檔案並填入正確的設定值"
    echo "   - QDRANT_HOST: Qdrant 服務地址"
    echo "   - QDRANT_API_KEY: Qdrant API 金鑰"
    echo "   - GCS_BUCKET_NAME: GCS 儲存桶名稱"
    echo "   - GOOGLE_APPLICATION_CREDENTIALS_FILE_PATH: 服務帳戶金鑰檔案路徑"
    echo ""
    read -p "按 Enter 繼續編輯 .env 檔案..."
    ${EDITOR:-nano} .env
fi

# 載入環境變數
source .env

# 檢查必要變數
if [ -z "$QDRANT_HOST" ] || [ -z "$GCS_BUCKET_NAME" ]; then
    echo "❌ 請在 .env 檔案中設定必要的環境變數"
    exit 1
fi

echo "✅ 環境變數檢查完成"

# 詢問部署選項
echo ""
echo "選擇部署步驟:"
echo "1) 只啟動 VM 上的備份 API (本地建構)"
echo "2) 建立並推送 Docker 映像檔到 Artifact Registry"
echo "3) 使用 Registry 映像檔啟動服務"
echo "4) 部署 Cloud Function"
echo "5) 設定 Cloud Scheduler"
echo "6) 完整部署 (全部)"
echo "7) 測試備份功能"

read -p "請選擇 (1-7): " choice

case $choice in
    1)
        echo "🔧 啟動 VM 備份 API (本地建構)..."
        docker-compose up -d
        echo "✅ 備份 API 已啟動，連接埠: 8081"
        echo "測試指令: curl http://localhost:8081/health"
        ;;
    2)
        echo "🔧 建立並推送 Docker 映像檔..."
        if [ -z "$GCP_PROJECT_ID" ]; then
            read -p "請輸入 GCP 專案 ID: " GCP_PROJECT_ID
            export GCP_PROJECT_ID
            echo "GCP_PROJECT_ID=$GCP_PROJECT_ID" >> .env
        fi
        ./build_image.sh
        ;;
    3)
        echo "🔧 使用 Registry 映像檔啟動服務..."
        if [ -z "$GCP_PROJECT_ID" ]; then
            read -p "請輸入 GCP 專案 ID: " GCP_PROJECT_ID
            export GCP_PROJECT_ID
        fi

        # 使用 registry 版本的 docker-compose
        docker-compose -f docker-compose.registry.yml up -d
        echo "✅ 備份 API 已啟動 (使用 Registry 映像檔)，連接埠: 8081"
        echo "測試指令: curl http://localhost:8081/health"
        ;;
    4)
        echo "🔧 部署 Cloud Function..."
        if [ -z "$GCP_PROJECT_ID" ]; then
            read -p "請輸入 GCP 專案 ID: " GCP_PROJECT_ID
            export GCP_PROJECT_ID
        fi

        # 取得 VM 內部 IP (如果在 GCP VM 上執行)
        if [ -z "$VM_BACKUP_API_URL" ]; then
            INTERNAL_IP=$(curl -s "http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/ip" -H "Metadata-Flavor: Google" 2>/dev/null || echo "")
            if [ -n "$INTERNAL_IP" ]; then
                export VM_BACKUP_API_URL="http://${INTERNAL_IP}:8081"
                echo "偵測到內部 IP: $INTERNAL_IP"
            else
                read -p "請輸入 VM 備份 API URL (例如: http://10.10.0.13:8081): " VM_BACKUP_API_URL
                export VM_BACKUP_API_URL
            fi
        fi

        cd cloud-function
        ./deploy.sh
        cd ..
        ;;
    5)
        echo "🔧 設定 Cloud Scheduler..."
        if [ -z "$GCP_PROJECT_ID" ]; then
            read -p "請輸入 GCP 專案 ID: " GCP_PROJECT_ID
            export GCP_PROJECT_ID
        fi
        ./setup-scheduler.sh
        ;;
    6)
        echo "🔧 執行完整部署..."

        # 檢查是否需要建立映像檔
        echo "選擇部署方式:"
        echo "a) 使用本地建構"
        echo "b) 建立 Registry 映像檔並使用"
        read -p "請選擇 (a/b): " deploy_method

        if [ -z "$GCP_PROJECT_ID" ]; then
            read -p "請輸入 GCP 專案 ID: " GCP_PROJECT_ID
            export GCP_PROJECT_ID
        fi

        if [[ $deploy_method == "b" ]]; then
            # 建立並推送映像檔
            echo "步驟 0: 建立並推送 Docker 映像檔..."
            ./build_image.sh

            echo "步驟 1: 啟動 VM 備份 API (使用 Registry 映像檔)..."
            docker-compose -f docker-compose.registry.yml up -d
        else
            echo "步驟 1: 啟動 VM 備份 API (本地建構)..."
            docker-compose up -d
        fi

        sleep 5

        # 檢查 API 狀態
        if curl -s http://localhost:8081/health >/dev/null; then
            echo "✅ VM 備份 API 啟動成功"
        else
            echo "❌ VM 備份 API 啟動失敗，請檢查 docker-compose logs"
            exit 1
        fi

        echo "步驟 2: 部署 Cloud Function..."
        if [ -z "$GCP_PROJECT_ID" ]; then
            read -p "請輸入 GCP 專案 ID: " GCP_PROJECT_ID
            export GCP_PROJECT_ID
        fi

        if [ -z "$VM_BACKUP_API_URL" ]; then
            INTERNAL_IP=$(curl -s "http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/ip" -H "Metadata-Flavor: Google" 2>/dev/null || echo "")
            if [ -n "$INTERNAL_IP" ]; then
                export VM_BACKUP_API_URL="http://${INTERNAL_IP}:8081"
            else
                read -p "請輸入 VM 備份 API URL: " VM_BACKUP_API_URL
                export VM_BACKUP_API_URL
            fi
        fi

        cd cloud-function
        ./deploy.sh
        cd ..

        # 步驟 3: 設定 Cloud Scheduler
        echo "步驟 3: 設定 Cloud Scheduler..."
        ./setup-scheduler.sh

        echo "🎉 完整部署完成！"
        ;;
    7)
        echo "🧪 測試備份功能..."

        # 測試 VM API
        echo "測試 VM 備份 API..."
        if curl -s http://localhost:8081/health; then
            echo "✅ VM API 健康檢查通過"
        else
            echo "❌ VM API 無回應"
        fi

        echo ""
        echo "列出 Qdrant collections..."
        curl -s http://localhost:8081/collections | python3 -m json.tool

        echo ""
        read -p "是否執行測試備份? (y/N): " test_backup
        if [[ $test_backup =~ ^[Yy]$ ]]; then
            echo "執行測試備份..."
            curl -X POST http://localhost:8081/backup \
                -H "Content-Type: application/json" \
                -d '{}' | python3 -m json.tool
        fi
        ;;
    *)
        echo "❌ 無效選擇"
        exit 1
        ;;
esac

echo ""
echo "📚 更多資訊請參考 README.md"
echo "📋 檢視服務狀態: docker-compose ps"
echo "📋 檢視服務日誌: docker-compose logs -f"
