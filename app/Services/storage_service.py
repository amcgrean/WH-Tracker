"""
Cloudflare R2 storage service (S3-compatible).

Usage:
    storage = StorageService()
    key = storage.upload_file(file_obj, 'rma/RMA123/receipt.jpg')
    url = storage.generate_presigned_url(key)
    storage.delete_file(key)

Requires env vars: R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET, R2_ENDPOINT_URL
"""

import mimetypes
from datetime import datetime

import boto3
from botocore.config import Config as BotoConfig
from flask import current_app


class StorageService:

    def __init__(self):
        self._client = None

    @property
    def _configured(self):
        """Return True if R2 credentials are present."""
        return bool(
            current_app.config.get('R2_ACCESS_KEY_ID')
            and current_app.config.get('R2_SECRET_ACCESS_KEY')
            and current_app.config.get('R2_ENDPOINT_URL')
        )

    @property
    def client(self):
        if self._client is None:
            if not self._configured:
                raise RuntimeError(
                    'R2 storage is not configured. Set R2_ACCESS_KEY_ID, '
                    'R2_SECRET_ACCESS_KEY, R2_ENDPOINT_URL, and R2_BUCKET.'
                )
            self._client = boto3.client(
                's3',
                endpoint_url=current_app.config['R2_ENDPOINT_URL'],
                aws_access_key_id=current_app.config['R2_ACCESS_KEY_ID'],
                aws_secret_access_key=current_app.config['R2_SECRET_ACCESS_KEY'],
                config=BotoConfig(
                    signature_version='s3v4',
                    retries={'max_attempts': 3, 'mode': 'adaptive'},
                ),
            )
        return self._client

    @property
    def bucket(self):
        return current_app.config.get('R2_BUCKET', 'wh-tracker-files')

    @property
    def is_available(self):
        """Check if R2 is configured and ready to use."""
        return self._configured

    # ── Upload ────────────────────────────────────────────────────────────────

    def upload_file(self, file_obj, object_key, content_type=None):
        """
        Upload a file-like object to R2.

        Args:
            file_obj: File-like object (e.g. from request.files)
            object_key: The key/path in the bucket (e.g. 'rma/RMA123/receipt.jpg')
            content_type: MIME type. Auto-detected from key if not provided.

        Returns:
            The object_key that was stored.
        """
        if not content_type:
            content_type = mimetypes.guess_type(object_key)[0] or 'application/octet-stream'

        self.client.upload_fileobj(
            file_obj,
            self.bucket,
            object_key,
            ExtraArgs={'ContentType': content_type},
        )
        return object_key

    def upload_bytes(self, data, object_key, content_type=None):
        """Upload raw bytes to R2."""
        if not content_type:
            content_type = mimetypes.guess_type(object_key)[0] or 'application/octet-stream'

        self.client.put_object(
            Bucket=self.bucket,
            Key=object_key,
            Body=data,
            ContentType=content_type,
        )
        return object_key

    # ── Download / URL ────────────────────────────────────────────────────────

    def generate_presigned_url(self, object_key, expires_in=3600):
        """
        Generate a presigned URL for downloading a file.

        Args:
            object_key: The key in the bucket.
            expires_in: URL lifetime in seconds (default 1 hour).

        Returns:
            A presigned URL string.
        """
        return self.client.generate_presigned_url(
            'get_object',
            Params={'Bucket': self.bucket, 'Key': object_key},
            ExpiresIn=expires_in,
        )

    def download_file(self, object_key):
        """Download a file and return the response body bytes."""
        response = self.client.get_object(Bucket=self.bucket, Key=object_key)
        return response['Body'].read()

    # ── Delete ───────────────────────────────────────��────────────────────────

    def delete_file(self, object_key):
        """Delete a file from R2."""
        self.client.delete_object(Bucket=self.bucket, Key=object_key)

    # ── Helpers ───────���───────────────────────────────────────────────────────

    @staticmethod
    def build_object_key(entity_type, entity_id, filename):
        """
        Build a standardised object key.

        Returns: '{entity_type}/{entity_id}/{timestamp}_{filename}'
        """
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        safe_name = filename.replace(' ', '_')
        return f'{entity_type}/{entity_id}/{timestamp}_{safe_name}'
