#!/bin/bash

# Cloud Function 部署腳本

set -e
source ../.env
# 設定變數
FUNCTION_NAME="qdrant-backup-trigger"
REGION="asia-east1"
PROJECT_ID=${GCP_PROJECT_ID}

# 檢查必要環境變數
if [ -z "$GCP_PROJECT_ID" ]; then
    echo "錯誤: 請設定 GCP_PROJECT_ID 環境變數"
    exit 1
fi

if [ -z "$VM_BACKUP_API_URL" ]; then
    echo "錯誤: 請設定 VM_BACKUP_API_URL 環境變數 (例如: http://10.10.0.13:8081)"
    exit 1
fi

echo "開始部署 Cloud Function..."
echo "函式名稱: $FUNCTION_NAME"
echo "專案 ID: $PROJECT_ID"
echo "區域: $REGION"
echo "VM API URL: $VM_BACKUP_API_URL"

# 部署 Cloud Function
gcloud functions deploy $FUNCTION_NAME \
    --gen2 \
    --runtime python311 \
    --region $REGION \
    --source . \
    --entry-point trigger_qdrant_backup \
    --trigger-http \
    --ingress-settings internal-only \
    --memory 512MB \
    --timeout 900s \
    --max-instances 10 \
    --project $PROJECT_ID \
    --vpc-connector qdrant-connector \

if [ $? -eq 0 ]; then
    echo "✅ Cloud Function 部署成功！"

    # 取得 Function URL
    FUNCTION_URL=$(gcloud functions describe $FUNCTION_NAME \
        --region $REGION \
        --project $PROJECT_ID \
        --format 'value(serviceConfig.uri)')

    echo "Function URL: $FUNCTION_URL"

    # 測試呼叫
    echo "測試 Cloud Function..."
    curl -X POST "$FUNCTION_URL" \
        -H "Content-Type: application/json" \
        -d '{}' \
        --max-time 30

    echo ""
    echo "部署完成！"
    echo ""
    echo "下一步: 設定 Cloud Scheduler"
    echo "執行以下指令來建立排程："
    echo ""
    echo "gcloud scheduler jobs create http qdrant-backup-hourly \\"
    echo "    --location=$REGION \\"
    echo "    --schedule='0 * * * *' \\"
    echo "    --uri='$FUNCTION_URL' \\"
    echo "    --http-method=POST \\"
    echo "    --headers='Content-Type=application/json' \\"
    echo "    --message-body='{}' \\"
    echo "    --project=$PROJECT_ID"

else
    echo "❌ Cloud Function 部署失敗！"
    exit 1
fi
