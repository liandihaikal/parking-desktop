import io
import os
from datetime import timedelta
from typing import Optional
from minio import Minio
from minio.error import S3Error
import cv2
from PIL import Image
from config import (
    MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY,
    MINIO_BUCKET, MINIO_SECURE, MINIO_REGION
)


class MinioService:
    def __init__(self):
        self.client = None
        self.bucket = MINIO_BUCKET
        self.region = MINIO_REGION
        self._connect()
        self._ensure_bucket()

    def _connect(self):
        try:
            endpoint = MINIO_ENDPOINT.replace('https://', '').replace('http://', '')

            print(f"[MINIO] Connecting to {endpoint} (secure={MINIO_SECURE})")

            self.client = Minio(
                endpoint,
                access_key=MINIO_ACCESS_KEY,
                secret_key=MINIO_SECRET_KEY,
                secure=MINIO_SECURE,
                region=self.region,
                # http_client=http_client  # Uncomment if SSL certificate issues
            )

            # Test connection
            self.client.list_buckets()
            print(f"[MINIO] ✅ Connected to {MINIO_ENDPOINT}")

        except Exception as e:
            print(f"[MINIO] ❌ Connection failed: {e}")
            self.client = None

    def _ensure_bucket(self):
        if not self.client:
            return

        try:
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
                print(f"[MINIO] 📦 Bucket '{self.bucket}' created")
            else:
                print(f"[MINIO] 📦 Bucket '{self.bucket}' already exists")
        except S3Error as e:
            print(f"[MINIO] ❌ Bucket error: {e}")

    def upload_image(self, image_data: bytes, object_name: str, content_type: str = 'image/jpeg') -> Optional[str]:
        if not self.client:
            print("[MINIO] ❌ Client not connected")
            return None

        try:
            image_stream = io.BytesIO(image_data)
            image_size = len(image_data)

            # Upload to MinIO/S3
            self.client.put_object(
                bucket_name=self.bucket,
                object_name=object_name,
                data=image_stream,
                length=image_size,
                content_type=content_type
            )

            # Generate presigned URL (valid for 7 days)
            url = self.client.presigned_get_object(
                bucket_name=self.bucket,
                object_name=object_name,
                expires=timedelta(days=7)
            )

            print(f"[MINIO] ✅ Uploaded: {object_name}")
            return url

        except S3Error as e:
            print(f"[MINIO] ❌ Upload failed: {e}")
            return None

    def upload_cv2_image(self, image: cv2.Mat, object_name: str, quality: int = 85) -> Optional[str]:
        if image is None:
            print("[MINIO] ❌ Image is None")
            return None

        try:
            # Convert OpenCV image (BGR) to RGB
            if len(image.shape) == 3:
                image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            else:
                image_rgb = image

            # Convert to PIL Image
            pil_image = Image.fromarray(image_rgb)

            # Save to bytes
            buffer = io.BytesIO()

            # Determine format from object name extension
            if object_name.lower().endswith('.png'):
                pil_image.save(buffer, format='PNG', optimize=True)
                content_type = 'image/png'
            else:
                pil_image.save(buffer, format='JPEG', quality=quality, optimize=True)
                content_type = 'image/jpeg'

            image_bytes = buffer.getvalue()

            return self.upload_image(image_bytes, object_name, content_type)

        except Exception as e:
            print(f"[MINIO] ❌ CV2 upload failed: {e}")
            return None

    def upload_file(self, file_path: str, object_name: str = None) -> Optional[str]:
        if not self.client:
            return None

        try:
            if not object_name:
                object_name = os.path.basename(file_path)

            with open(file_path, 'rb') as file:
                file_data = file.read()

            # Determine content type
            if file_path.lower().endswith('.jpg') or file_path.lower().endswith('.jpeg'):
                content_type = 'image/jpeg'
            elif file_path.lower().endswith('.png'):
                content_type = 'image/png'
            else:
                content_type = 'application/octet-stream'

            return self.upload_image(file_data, object_name, content_type)

        except Exception as e:
            print(f"[MINIO] ❌ File upload failed: {e}")
            return None

    def delete_object(self, object_name: str) -> bool:
        if not self.client:
            return False

        try:
            self.client.remove_object(self.bucket, object_name)
            print(f"[MINIO] 🗑️ Deleted: {object_name}")
            return True
        except S3Error as e:
            print(f"[MINIO] ❌ Delete failed: {e}")
            return False

    def get_object_url(self, object_name: str, expires: timedelta = timedelta(days=7)) -> Optional[str]:
        if not self.client:
            return None

        try:
            url = self.client.presigned_get_object(
                bucket_name=self.bucket,
                object_name=object_name,
                expires=expires
            )
            return url
        except S3Error as e:
            print(f"[MINIO] ❌ Get URL failed: {e}")
            return None

    def object_exists(self, object_name: str) -> bool:
        """Check if object exists in bucket"""
        if not self.client:
            return False

        try:
            self.client.stat_object(self.bucket, object_name)
            return True
        except S3Error:
            return False

    def generate_object_name(self, ticket_number: str, capture_type: str = 'checkin') -> str:
        from datetime import datetime

        now = datetime.now()
        date_path = now.strftime('%Y/%m/%d')
        timestamp = now.strftime('%Y%m%d_%H%M%S')

        return f"{capture_type}/{date_path}/{ticket_number}_{timestamp}.jpg"
