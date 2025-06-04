#!/usr/bin/env python3
"""
Qdrant 備份 API 服務
提供 HTTP API 來觸發 Qdrant collection 備份並上傳到 GCS
"""

import os
import json
import logging
import requests
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

from flask import Flask, request, jsonify
from google.cloud import storage

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# 環境變數設定
QDRANT_HOST = os.getenv('QDRANT_HOST', 'localhost')
QDRANT_PORT = os.getenv('QDRANT_PORT', '6333')
QDRANT_API_KEY = os.getenv('QDRANT_API_KEY', '')
GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME', 'csfiledata.ariel.com.tw')
GCS_FOLDER_PREFIX = os.getenv('GCS_FOLDER_PREFIX', 'qdrant')
BACKUP_LOCAL_PATH = os.getenv('BACKUP_LOCAL_PATH', '/tmp/qdrant_snapshots')

# 確保備份目錄存在
Path(BACKUP_LOCAL_PATH).mkdir(parents=True, exist_ok=True)


class QdrantBackupService:
    """Qdrant 備份服務類別"""

    def __init__(self):
        self.qdrant_url = f"http://{QDRANT_HOST}:{QDRANT_PORT}"
        self.headers = {}
        if QDRANT_API_KEY:
            self.headers['api-key'] = QDRANT_API_KEY

        # 初始化 GCS 客戶端
        self.gcs_client = storage.Client()
        self.bucket = self.gcs_client.bucket(GCS_BUCKET_NAME)

    def get_collections(self) -> list:
        """取得所有 collection 列表"""
        try:
            response = requests.get(f"{self.qdrant_url}/collections",
                                    headers=self.headers,
                                    timeout=30)
            response.raise_for_status()

            data = response.json()
            collections = [
                collection['name']
                for collection in data.get('result', {}).get(
                    'collections', [])
            ]
            logger.info(f"找到 {len(collections)} 個 collections: {collections}")
            return collections

        except Exception as e:
            logger.error(f"取得 collections 失敗: {e}")
            raise

    def create_snapshot(self, collection_name: str) -> str:
        """為指定 collection 建立 snapshot"""
        try:
            # 建立 snapshot
            response = requests.post(
                f"{self.qdrant_url}/collections/{collection_name}/snapshots",
                headers=self.headers,
                timeout=300  # 5分鐘超時
            )
            response.raise_for_status()

            data = response.json()
            snapshot_name = data.get('result', {}).get('name')

            if not snapshot_name:
                raise ValueError(f"無法取得 snapshot 名稱: {data}")

            logger.info(
                f"Collection '{collection_name}' snapshot 建立成功: {snapshot_name}"
            )
            return snapshot_name

        except Exception as e:
            logger.error(
                f"建立 snapshot 失敗 (collection: {collection_name}): {e}")
            raise

    def download_snapshot(self, collection_name: str,
                          snapshot_name: str) -> str:
        """下載 snapshot 檔案"""
        try:
            # 下載 snapshot
            response = requests.get(
                f"{self.qdrant_url}/collections/{collection_name}/snapshots/{snapshot_name}",
                headers=self.headers,
                stream=True,
                timeout=600  # 10分鐘超時
            )
            response.raise_for_status()

            # 儲存到本地
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            local_filename = f"{collection_name}_{timestamp}_{snapshot_name}"
            local_path = os.path.join(BACKUP_LOCAL_PATH, local_filename)

            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            logger.info(f"Snapshot 下載完成: {local_path}")
            return local_path

        except Exception as e:
            logger.error(f"下載 snapshot 失敗: {e}")
            raise

    def upload_to_gcs(self, local_path: str, collection_name: str) -> str:
        """上傳備份檔案到 GCS"""
        try:
            filename = os.path.basename(local_path)
            timestamp = datetime.now().strftime("%Y/%m/%d")
            gcs_path = f"{GCS_FOLDER_PREFIX}/{timestamp}/{filename}"

            blob = self.bucket.blob(gcs_path)
            blob.upload_from_filename(local_path)

            logger.info(f"檔案上傳到 GCS 成功: gs://{GCS_BUCKET_NAME}/{gcs_path}")
            return gcs_path

        except Exception as e:
            logger.error(f"上傳到 GCS 失敗: {e}")
            raise

    def cleanup_local_file(self, local_path: str):
        """清理本地檔案"""
        try:
            if os.path.exists(local_path):
                os.remove(local_path)
                logger.info(f"本地檔案清理完成: {local_path}")
        except Exception as e:
            logger.warning(f"清理本地檔案失敗: {e}")

    def delete_snapshot(self, collection_name: str, snapshot_name: str):
        """刪除 Qdrant 上的 snapshot"""
        try:
            response = requests.delete(
                f"{self.qdrant_url}/collections/{collection_name}/snapshots/{snapshot_name}",
                headers=self.headers,
                timeout=30)
            response.raise_for_status()
            logger.info(
                f"Qdrant snapshot 刪除完成: {collection_name}/{snapshot_name}")
        except Exception as e:
            logger.warning(f"刪除 Qdrant snapshot 失敗: {e}")

    def backup_collection(self, collection_name: str) -> Dict[str, Any]:
        """備份單個 collection"""
        result = {
            'collection': collection_name,
            'success': False,
            'snapshot_name': None,
            'gcs_path': None,
            'error': None
        }

        local_path = None
        snapshot_name = None

        try:
            # 1. 建立 snapshot
            snapshot_name = self.create_snapshot(collection_name)
            result['snapshot_name'] = snapshot_name

            # 2. 下載 snapshot
            local_path = self.download_snapshot(collection_name, snapshot_name)

            # 3. 上傳到 GCS
            gcs_path = self.upload_to_gcs(local_path, collection_name)
            result['gcs_path'] = gcs_path

            # 4. 清理
            self.cleanup_local_file(local_path)
            self.delete_snapshot(collection_name, snapshot_name)

            result['success'] = True
            logger.info(f"Collection '{collection_name}' 備份完成")

        except Exception as e:
            result['error'] = str(e)
            logger.error(f"Collection '{collection_name}' 備份失敗: {e}")

            # 清理失敗的檔案
            if local_path:
                self.cleanup_local_file(local_path)
            if snapshot_name:
                self.delete_snapshot(collection_name, snapshot_name)

        return result

    def backup_all_collections(self) -> Dict[str, Any]:
        """備份所有 collections"""
        start_time = datetime.now()

        try:
            collections = self.get_collections()

            if not collections:
                return {
                    'success': False,
                    'message': '沒有找到任何 collections',
                    'collections': [],
                    'duration_seconds': 0
                }

            results = []
            success_count = 0

            for collection_name in collections:
                logger.info(f"開始備份 collection: {collection_name}")
                result = self.backup_collection(collection_name)
                results.append(result)

                if result['success']:
                    success_count += 1

            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            return {
                'success': success_count > 0,
                'message': f'備份完成: {success_count}/{len(collections)} 成功',
                'total_collections': len(collections),
                'success_count': success_count,
                'failed_count': len(collections) - success_count,
                'collections': results,
                'start_time': start_time.isoformat(),
                'end_time': end_time.isoformat(),
                'duration_seconds': duration
            }

        except Exception as e:
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            return {
                'success': False,
                'message': f'備份過程發生錯誤: {str(e)}',
                'error': str(e),
                'start_time': start_time.isoformat(),
                'end_time': end_time.isoformat(),
                'duration_seconds': duration
            }


# 初始化備份服務
backup_service = QdrantBackupService()


@app.route('/health', methods=['GET'])
def health_check():
    """健康檢查端點"""
    return jsonify({
        'status': 'healthy',
        'service': 'qdrant-backup-api',
        'timestamp': datetime.now().isoformat()
    })


@app.route('/backup', methods=['POST'])
def backup_endpoint():
    """觸發備份的主要端點"""
    try:
        # 檢查請求資料
        data = request.get_json() or {}
        collection_name = data.get('collection')

        if collection_name:
            # 備份指定 collection
            logger.info(f"開始備份指定 collection: {collection_name}")
            result = backup_service.backup_collection(collection_name)

            if result['success']:
                return jsonify(result), 200
            else:
                return jsonify(result), 500
        else:
            # 備份所有 collections
            logger.info("開始備份所有 collections")
            result = backup_service.backup_all_collections()

            if result['success']:
                return jsonify(result), 200
            else:
                return jsonify(result), 500

    except Exception as e:
        logger.error(f"備份 API 錯誤: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


@app.route('/collections', methods=['GET'])
def list_collections():
    """列出所有 collections"""
    try:
        collections = backup_service.get_collections()
        return jsonify({
            'success': True,
            'collections': collections,
            'count': len(collections)
        })
    except Exception as e:
        logger.error(f"取得 collections 失敗: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/status', methods=['GET'])
def status():
    """檢查 Qdrant 連線狀態"""
    try:
        response = requests.get(f"{backup_service.qdrant_url}/collections",
                                headers=backup_service.headers,
                                timeout=10)
        response.raise_for_status()

        return jsonify({
            'qdrant_status': 'connected',
            'qdrant_url': backup_service.qdrant_url,
            'gcs_bucket': GCS_BUCKET_NAME,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            'qdrant_status': 'disconnected',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 503


if __name__ == '__main__':
    # 檢查必要的環境變數
    required_env_vars = ['GCS_BUCKET_NAME']
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]

    if missing_vars:
        logger.error(f"缺少必要的環境變數: {missing_vars}")
        exit(1)

    logger.info("Qdrant 備份 API 服務啟動中...")
    logger.info(f"Qdrant URL: {backup_service.qdrant_url}")
    logger.info(f"GCS Bucket: {GCS_BUCKET_NAME}")
    logger.info(f"備份路徑: {BACKUP_LOCAL_PATH}")

    app.run(host='0.0.0.0', port=8080, debug=False)
