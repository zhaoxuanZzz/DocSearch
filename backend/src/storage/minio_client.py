"""MinIO object storage client."""

import io
from typing import BinaryIO

from minio import Minio
from minio.error import S3Error

from src.core.config import settings

_client: Minio | None = None


def get_minio_client() -> Minio:
    global _client
    if _client is None:
        _client = Minio(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        # Ensure bucket exists
        if not _client.bucket_exists(settings.minio_bucket):
            _client.make_bucket(settings.minio_bucket)
    return _client


def original_object_key(doc_id: int, file_name: str) -> str:
    return f"originals/{doc_id}/{file_name}"


def markdown_object_key(doc_id: int) -> str:
    return f"markdown/{doc_id}/converted.md"


def upload_original(doc_id: int, file_name: str, data: BinaryIO, size: int, content_type: str) -> str:
    """Upload the original document file and return the MinIO object key."""
    client = get_minio_client()
    key = original_object_key(doc_id, file_name)
    client.put_object(
        bucket_name=settings.minio_bucket,
        object_name=key,
        data=data,
        length=size,
        content_type=content_type,
    )
    return key


def upload_markdown(doc_id: int, markdown_content: str) -> str:
    """Upload Docling-converted Markdown and return the MinIO object key."""
    client = get_minio_client()
    key = markdown_object_key(doc_id)
    encoded = markdown_content.encode("utf-8")
    client.put_object(
        bucket_name=settings.minio_bucket,
        object_name=key,
        data=io.BytesIO(encoded),
        length=len(encoded),
        content_type="text/markdown; charset=utf-8",
    )
    return key


def download_file(object_key: str) -> bytes:
    """Download an object and return its bytes."""
    client = get_minio_client()
    response = client.get_object(settings.minio_bucket, object_key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def download_markdown(doc_id: int) -> str:
    """Download and return the Markdown text for a document."""
    return download_file(markdown_object_key(doc_id)).decode("utf-8")


def delete_document_objects(doc_id: int, file_name: str) -> None:
    """Delete all MinIO objects associated with a document."""
    client = get_minio_client()
    keys_to_delete = [
        original_object_key(doc_id, file_name),
        markdown_object_key(doc_id),
    ]
    for key in keys_to_delete:
        try:
            client.remove_object(settings.minio_bucket, key)
        except S3Error:
            pass  # Object may not exist (e.g., non-PDF/DOCX has no markdown)


def get_presigned_url(object_key: str, expires_seconds: int = 3600) -> str:
    """Generate a presigned download URL."""
    from datetime import timedelta

    client = get_minio_client()
    return client.presigned_get_object(
        settings.minio_bucket,
        object_key,
        expires=timedelta(seconds=expires_seconds),
    )


class MinioClient:
    """OOP wrapper around the module-level MinIO helper functions."""

    def upload_original(self, doc_id: int, file_name: str, data: bytes) -> str:
        """Upload raw file bytes; size is derived from data."""
        import mimetypes
        content_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
        return upload_original(doc_id, file_name, io.BytesIO(data), len(data), content_type)

    def upload_markdown(self, doc_id: int, markdown_content: str) -> str:
        return upload_markdown(doc_id, markdown_content)

    def download_original(self, doc_id: int, file_name: str) -> bytes:
        return download_file(original_object_key(doc_id, file_name))

    def download_markdown(self, doc_id: int) -> bytes:
        return download_file(markdown_object_key(doc_id))

    def delete_document(self, doc_id: int, file_name: str, fmt: str | None = None) -> None:
        delete_document_objects(doc_id, file_name)

    def get_presigned_url(self, object_key: str, expires_seconds: int = 3600) -> str:
        return get_presigned_url(object_key, expires_seconds)
