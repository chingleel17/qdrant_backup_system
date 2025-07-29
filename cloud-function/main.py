import os
import json
import logging
import requests
from datetime import datetime
from typing import Any, Dict

import functions_framework
from google.cloud import logging as cloud_logging

# 設定 Cloud Logging
client = cloud_logging.Client()
client.setup_logging()

logger = logging.getLogger(__name__)

# 環境變數
VM_BACKUP_API_URL = os.getenv(
    'VM_BACKUP_API_URL')  # 例如: http://10.10.1.13:8081
BACKUP_API_TIMEOUT = int(os.getenv('BACKUP_API_TIMEOUT', '900'))  # 15分鐘
AUTHORIZATION_TOKEN = os.getenv('AUTHORIZATION_TOKEN', '')  # 可選的認證 token

LOG_PREFIX = "[QDRANT-BACKUP-CLOUD-FUNCTION]"


def log_info(msg, *args, **kwargs):
    logger.info(f"{LOG_PREFIX} {msg}", *args, **kwargs)


def log_error(msg, *args, **kwargs):
    logger.error(f"{LOG_PREFIX} {msg}", *args, **kwargs)


def log_warning(msg, *args, **kwargs):
    logger.warning(f"{LOG_PREFIX} {msg}", *args, **kwargs)


def log_exception(msg, *args, exc_info=True, **kwargs):
    logger.exception(f"{LOG_PREFIX} {msg}", *args, exc_info=exc_info, **kwargs)


@functions_framework.http
def trigger_qdrant_backup(request):
    """
    Cloud Function 主要函式，由 Cloud Scheduler 觸發
    呼叫 VM 上的備份 API 來執行 Qdrant 備份
    """
    start_time = datetime.now()

    try:
        # 驗證環境變數
        if not VM_BACKUP_API_URL:
            error_msg = "缺少必要的環境變數: VM_BACKUP_API_URL"
            log_error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'timestamp': start_time.isoformat()
            }, 500

        # 準備請求 headers
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'GCP-CloudFunction-QdrantBackup/1.0'
        }

        if AUTHORIZATION_TOKEN:
            headers['Authorization'] = f'Bearer {AUTHORIZATION_TOKEN}'

        # 檢查請求參數
        request_json = request.get_json(silent=True) or {}
        collection_name = request_json.get('collection')

        # 準備備份請求資料
        backup_data = {}
        if collection_name:
            backup_data['collection'] = collection_name
            log_info(f"開始觸發指定 collection 備份: {collection_name}")
        else:
            log_info("開始觸發所有 collections 備份")

        # 呼叫 VM 上的備份 API
        backup_url = f"{VM_BACKUP_API_URL.rstrip('/')}/backup"

        log_info(f"呼叫備份 API: {backup_url}")

        response = requests.post(backup_url,
                                 json=backup_data,
                                 headers=headers,
                                 timeout=BACKUP_API_TIMEOUT)

        # 檢查回應狀態
        if response.status_code == 200:
            result = response.json()
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            success_count = 0
            total_count = 0

            if result.get('collections'):
                success_count = result.get('success_count', 0)
                total_count = result.get('total_collections', 0)

            # 記錄成功日誌
            log_info(
                f"備份觸發成功，耗時: {duration:.2f}秒，備份結果: {success_count}/{total_count}成功"
            )

            return {
                'success': True,
                'message': '備份觸發成功',
                'backup_result': result,
                'cloud_function_duration_seconds': duration,
                'timestamp': start_time.isoformat()
            }, 200

        else:
            # 備份 API 回傳錯誤
            error_msg = f"備份 API 呼叫失敗，狀態碼: {response.status_code}"
            log_error(f"{error_msg}, 回應: {response.text}")

            try:
                error_response = response.json()
            except:
                error_response = {'raw_response': response.text}

            return {
                'success': False,
                'error': error_msg,
                'api_response': error_response,
                'status_code': response.status_code,
                'timestamp': start_time.isoformat()
            }, 500

    except requests.exceptions.Timeout:
        error_msg = f"備份 API 呼叫超時 (超過 {BACKUP_API_TIMEOUT} 秒)"
        log_error(error_msg)
        return {
            'success': False,
            'error': error_msg,
            'timeout_seconds': BACKUP_API_TIMEOUT,
            'timestamp': start_time.isoformat()
        }, 504

    except requests.exceptions.ConnectionError as e:
        error_msg = f"無法連線到備份 API: {str(e)}"
        log_error(error_msg)
        return {
            'success': False,
            'error': error_msg,
            'api_url': VM_BACKUP_API_URL,
            'timestamp': start_time.isoformat()
        }, 503

    except Exception as e:
        error_msg = f"Cloud Function 執行錯誤: {str(e)}"
        log_exception(error_msg)
        return {
            'success': False,
            'error': error_msg,
            'timestamp': start_time.isoformat()
        }, 500


@functions_framework.http
def health_check(request):
    """健康檢查端點"""
    try:
        # 檢查環境變數
        config_status = {
            'vm_backup_api_url': bool(VM_BACKUP_API_URL),
            'authorization_configured': bool(AUTHORIZATION_TOKEN),
            'timeout_seconds': BACKUP_API_TIMEOUT
        }

        # 可選：ping 備份 API
        api_status = 'unknown'
        if VM_BACKUP_API_URL:
            try:
                health_url = f"{VM_BACKUP_API_URL.rstrip('/')}/health"
                response = requests.get(health_url, timeout=10)
                api_status = 'healthy' if response.status_code == 200 else 'unhealthy'
            except:
                api_status = 'unreachable'

        return {
            'status': 'healthy',
            'service': 'qdrant-backup-cloud-function',
            'config': config_status,
            'backup_api_status': api_status,
            'timestamp': datetime.now().isoformat()
        }, 200

    except Exception as e:
        log_exception("健康檢查失敗", exc_info=True)
        return {
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }, 500


# 如果在本地測試
if __name__ == '__main__':
    from flask import Flask, request as flask_request

    app = Flask(__name__)

    @app.route('/trigger-backup', methods=['POST'])
    def local_trigger():
        return trigger_qdrant_backup(flask_request)

    @app.route('/health', methods=['GET'])
    def local_health():
        return health_check(flask_request)

    app.run(host='0.0.0.0', port=8080, debug=True)
