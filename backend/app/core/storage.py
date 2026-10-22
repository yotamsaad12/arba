"""File storage behind one interface: local disk in dev and tests, S3 in production.

Browsers upload and download directly against short-lived URLs, so the API never holds file
bodies in memory. Locally those URLs point back at this API (see api/v1/storage.py) and are
signed JWTs; on S3 they are presigned S3 URLs.
"""

import asyncio
import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

import jwt

from app.core.config import settings

_ALGORITHM = "HS256"
_AUDIENCE = "arba-storage"


@dataclass
class PresignedUpload:
    url: str
    method: str = "PUT"
    headers: dict[str, str] = field(default_factory=dict)


class Storage(Protocol):
    def presign_upload(self, key: str, content_type: str, max_bytes: int) -> PresignedUpload: ...
    def presign_download(self, key: str, file_name: str, content_type: str) -> str: ...
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...
    async def get(self, key: str) -> bytes: ...
    async def size(self, key: str) -> int | None: ...
    async def delete(self, key: str) -> None: ...


def content_disposition(file_name: str) -> str:
    """Always an attachment: uploaded HTML or SVG must never render on our origin."""
    ascii_name = file_name.encode("ascii", "ignore").decode() or "file"
    ascii_name = ascii_name.replace('"', "").replace("\\", "")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(file_name)}"


def _expiry() -> datetime:
    return datetime.now(UTC) + timedelta(minutes=settings.upload_url_minutes)


class SignedUrlStorage:
    """Storage whose upload and download links point back at this API (api/v1/storage.py),
    as signed, short-lived JWTs."""

    url_prefix = "/api/v1/storage"

    def _token(self, claims: dict[str, object]) -> str:
        payload = {**claims, "aud": _AUDIENCE, "exp": _expiry()}
        return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGORITHM)

    def presign_upload(self, key: str, content_type: str, max_bytes: int) -> PresignedUpload:
        token = self._token({"op": "put", "key": key, "ct": content_type, "max": max_bytes})
        return PresignedUpload(
            url=f"{self.url_prefix}/{token}", headers={"Content-Type": content_type}
        )

    def presign_download(self, key: str, file_name: str, content_type: str) -> str:
        token = self._token({"op": "get", "key": key, "ct": content_type, "fn": file_name})
        return f"{self.url_prefix}/{token}"

    @staticmethod
    def verify(token: str, op: str) -> dict[str, object] | None:
        try:
            claims = jwt.decode(
                token, settings.jwt_secret, algorithms=[_ALGORITHM], audience=_AUDIENCE
            )
        except jwt.PyJWTError:
            return None
        return claims if claims.get("op") == op else None

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        raise NotImplementedError

    async def get(self, key: str) -> bytes:
        raise NotImplementedError


class LocalStorage(SignedUrlStorage):
    def __init__(self, root: Path, url_prefix: str = "/api/v1/storage"):
        self.root = root.resolve()
        self.url_prefix = url_prefix

    def path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise ValueError("storage key escapes the storage root")
        return path

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        await asyncio.to_thread(self._write, key, data)

    def _write(self, key: str, data: bytes) -> None:
        path = self.path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{uuid.uuid4().hex}.part")
        tmp.write_bytes(data)
        os.replace(tmp, path)

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(self.path(key).read_bytes)

    async def size(self, key: str) -> int | None:
        path = self.path(key)
        return path.stat().st_size if path.exists() else None

    async def delete(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)


class S3Storage:
    def __init__(self, bucket: str, region: str | None, endpoint_url: str | None):
        import boto3

        self.bucket = bucket
        self.client = boto3.client("s3", region_name=region, endpoint_url=endpoint_url)

    def presign_upload(self, key: str, content_type: str, max_bytes: int) -> PresignedUpload:
        # A presigned PUT can't cap the size; the API checks it when the upload is completed.
        url = self.client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self.bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=settings.upload_url_minutes * 60,
        )
        return PresignedUpload(url=url, headers={"Content-Type": content_type})

    def presign_download(self, key: str, file_name: str, content_type: str) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                "ResponseContentDisposition": content_disposition(file_name),
                "ResponseContentType": content_type,
            },
            ExpiresIn=settings.upload_url_minutes * 60,
        )

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        await asyncio.to_thread(
            self.client.put_object,
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            ServerSideEncryption="aws:kms",
        )

    async def get(self, key: str) -> bytes:
        response = await asyncio.to_thread(self.client.get_object, Bucket=self.bucket, Key=key)
        return await asyncio.to_thread(response["Body"].read)

    async def size(self, key: str) -> int | None:
        from botocore.exceptions import ClientError

        try:
            head = await asyncio.to_thread(self.client.head_object, Bucket=self.bucket, Key=key)
        except ClientError:
            return None
        return int(head["ContentLength"])

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self.client.delete_object, Bucket=self.bucket, Key=key)


@lru_cache
class DatabaseStorage(SignedUrlStorage):
    """Files in Postgres, for hosts without a lasting disk (serverless). Fine for documents of
    a few megabytes; S3 is the step up when volumes grow."""

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        from sqlalchemy.dialects.postgresql import insert

        from app.db.models import StoredFile
        from app.db.session import SessionLocal

        async with SessionLocal() as db:
            values = {"key": key, "content_type": content_type, "data": data, "size": len(data)}
            await db.execute(
                insert(StoredFile)
                .values(**values)
                .on_conflict_do_update(index_elements=["key"], set_=values)
            )
            await db.commit()

    async def get(self, key: str) -> bytes:
        from app.db.models import StoredFile
        from app.db.session import SessionLocal

        async with SessionLocal() as db:
            row = await db.get(StoredFile, key)
        if row is None:
            raise FileNotFoundError(key)
        return row.data

    async def size(self, key: str) -> int | None:
        from sqlalchemy import select

        from app.db.models import StoredFile
        from app.db.session import SessionLocal

        async with SessionLocal() as db:
            return await db.scalar(select(StoredFile.size).where(StoredFile.key == key))

    async def delete(self, key: str) -> None:
        from sqlalchemy import delete

        from app.db.models import StoredFile
        from app.db.session import SessionLocal

        async with SessionLocal() as db:
            await db.execute(delete(StoredFile).where(StoredFile.key == key))
            await db.commit()


def get_storage() -> Storage:
    if settings.storage_backend == "database":
        return DatabaseStorage()
    if settings.storage_backend == "s3":
        assert settings.s3_bucket
        return S3Storage(settings.s3_bucket, settings.s3_region, settings.s3_endpoint_url)
    return LocalStorage(settings.storage_dir)
