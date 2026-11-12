"""S3 (MinIO) access.

Two kinds of clients:
* internal client (http://minio:9000) for server-side calls from api and worker;
* signing clients bound to the public host the browser used. URLs are signed for
  https://<host>/<bucket>/<key> and returned as /storage/<bucket>/<key>?..., Caddy strips the prefix
  and keeps the Host header, so the signature MinIO checks is exactly what we signed.
  Presigning is local HMAC, no network call.
"""

import asyncio
import re
from functools import lru_cache
from typing import Any
from urllib.parse import urlsplit

import boto3
from botocore.config import Config

from app.core.config import get_settings

_HOST_RE = re.compile(r"^[A-Za-z0-9.\-]+(:\d{1,5})?$|^\[[0-9A-Fa-f:.]+\](:\d{1,5})?$")


def _client(endpoint: str) -> Any:
    s = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=s.s3_region,
        aws_access_key_id=s.s3_access_key,
        aws_secret_access_key=s.s3_secret_key,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            retries={"max_attempts": 3, "mode": "standard"},
            connect_timeout=5,
            read_timeout=60,
        ),
    )


@lru_cache
def internal_client() -> Any:
    return _client(get_settings().s3_endpoint)


@lru_cache(maxsize=32)
def _signing_client(host: str) -> Any:
    return _client(f"https://{host}")


def safe_host(host: str | None) -> str:
    """Host header from the request; validated because it ends up in signed URLs."""
    if not host or not _HOST_RE.match(host):
        return "localhost"
    return host


def _to_public(url: str) -> str:
    parts = urlsplit(url)
    return f"{get_settings().storage_public_prefix}{parts.path}?{parts.query}"


def presign_get(
    host: str,
    bucket: str,
    key: str,
    ttl: int,
    *,
    content_type: str | None = None,
    filename: str | None = None,
) -> str:
    params: dict[str, Any] = {"Bucket": bucket, "Key": key}
    if content_type:
        params["ResponseContentType"] = content_type
    if filename:
        params["ResponseContentDisposition"] = f'inline; filename="{filename}"'
    url = _signing_client(safe_host(host)).generate_presigned_url("get_object", Params=params, ExpiresIn=ttl)
    return _to_public(url)


def presign_upload_part(host: str, bucket: str, key: str, upload_id: str, part_number: int, ttl: int) -> str:
    url = _signing_client(safe_host(host)).generate_presigned_url(
        "upload_part",
        Params={"Bucket": bucket, "Key": key, "UploadId": upload_id, "PartNumber": part_number},
        ExpiresIn=ttl,
    )
    return _to_public(url)


# --- server-side operations (blocking boto3 calls are moved to a thread) ---------------------


async def create_multipart(bucket: str, key: str, content_type: str) -> str:
    resp = await asyncio.to_thread(
        internal_client().create_multipart_upload, Bucket=bucket, Key=key, ContentType=content_type
    )
    return resp["UploadId"]


async def complete_multipart(bucket: str, key: str, upload_id: str, parts: list[dict]) -> None:
    await asyncio.to_thread(
        internal_client().complete_multipart_upload,
        Bucket=bucket,
        Key=key,
        UploadId=upload_id,
        MultipartUpload={"Parts": parts},
    )


async def abort_multipart(bucket: str, key: str, upload_id: str) -> None:
    await asyncio.to_thread(
        internal_client().abort_multipart_upload, Bucket=bucket, Key=key, UploadId=upload_id
    )


async def object_size(bucket: str, key: str) -> int:
    resp = await asyncio.to_thread(internal_client().head_object, Bucket=bucket, Key=key)
    return int(resp["ContentLength"])


async def delete_prefix(bucket: str, prefix: str) -> None:
    def _delete() -> None:
        client = internal_client()
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            keys = [{"Key": o["Key"]} for o in page.get("Contents", [])]
            if keys:
                client.delete_objects(Bucket=bucket, Delete={"Objects": keys, "Quiet": True})

    await asyncio.to_thread(_delete)


def upload_file_sync(path: str, bucket: str, key: str, content_type: str) -> None:
    internal_client().upload_file(path, bucket, key, ExtraArgs={"ContentType": content_type})


def download_file_sync(bucket: str, key: str, path: str) -> None:
    internal_client().download_file(bucket, key, path)
