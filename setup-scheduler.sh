#!/bin/bash

# Cloud Scheduler 設定腳本

set -e

# 設定變數
JOB_NAME="qdrant-backup-hourly"
REGION="asia-east1"
PROJECT_ID=${GCP_PROJECT_ID}
FUNCTION_NAME="qdrant-backup-trigger"

# 檢查必要環境變數
if [ -z "$GCP_PROJECT_ID" ]; then
    echo "錯誤: 請設定 GCP_PROJECT_ID 環境變數"
    exit 1
fi

echo "設定 Cloud Scheduler..."
echo "排程名稱: $JOB_NAME"
echo "專案 ID: $PROJECT_ID"
echo "區域: $REGION"

# 取得 Cloud Function URL
echo "取得 Cloud Function URL..."
FUNCTION_URL=$(gcloud functions describe $FUNCTION_NAME \
    --region $REGION \
    --project $PROJECT_ID \
    --format 'value(serviceConfig.uri)' 2>/dev/null)

if [ -z "$FUNCTION_URL" ]; then
    echo "錯誤: 找不到 Cloud Function '$FUNCTION_NAME'"
    echo "請先部署 Cloud Function"
    exit 1
fi

echo "Function URL: $FUNCTION_URL"

# 檢查是否已存在排程
if gcloud scheduler jobs describe $JOB_NAME --location=$REGION --project=$PROJECT_ID >/dev/null 2>&1; then
    echo "排程 '$JOB_NAME' 已存在，正在更新..."

    gcloud scheduler jobs update http $JOB_NAME \
        --location=$REGION \
        --schedule='0 * * * *' \
        --uri="$FUNCTION_URL" \
        --http-method=POST \
        --headers='Content-Type=application/json' \
        --message-body='{}' \
        --project=$PROJECT_ID
else
    echo "建立新排程 '$JOB_NAME'..."

    gcloud scheduler jobs create http $JOB_NAME \
        --location=$REGION \
        --schedule='0 * * * *' \
        --uri="$FUNCTION_URL" \
        --http-method=POST \
        --headers='Content-Type=application/json' \
        --message-body='{}' \
        --project=$PROJECT_ID
fi

if [ $? -eq 0 ]; then
    echo "✅ Cloud Scheduler 設定成功！"

    # 顯示排程資訊
    echo ""
    echo "排程資訊:"
    gcloud scheduler jobs describe $JOB_NAME \
        --location=$REGION \
        --project=$PROJECT_ID \
        --format='table(name,schedule,state,httpTarget.uri)'

    echo ""
    echo "手動觸發測試:"
    echo "gcloud scheduler jobs run $JOB_NAME --location=$REGION --project=$PROJECT_ID"

    echo ""
    echo "檢視執行日誌:"
    echo "gcloud logging read \"resource.type=cloud_function AND resource.labels.function_name=$FUNCTION_NAME\" --limit=50 --format='table(timestamp,severity,textPayload)' --project=$PROJECT_ID"

else
    echo "❌ Cloud Scheduler 設定失敗！"
    exit 1
fi
