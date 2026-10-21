"""Signed upload and download URLs for the local storage backend (dev and tests).

With S3 the browser talks to S3 directly and these routes are never used.
"""

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import FileResponse

from app.core.errors import AppError, not_found
from app.core.storage import LocalStorage, content_disposition, get_storage

router = APIRouter(prefix="/storage", tags=["storage"], include_in_schema=False)


def _local() -> LocalStorage:
    storage = get_storage()
    if not isinstance(storage, LocalStorage):
        raise not_found("storage")
    return storage


@router.put("/{token}", status_code=status.HTTP_204_NO_CONTENT)
async def upload(token: str, request: Request) -> Response:
    storage = _local()
    claims = storage.verify(token, "put")
    if claims is None:
        raise AppError(403, "invalid_upload_url", "upload link is invalid or expired")
    limit = int(claims["max"])  # type: ignore[call-overload]
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > limit:
            raise AppError(413, "file_too_large", "file is too large")
    await storage.put(str(claims["key"]), bytes(data), str(claims["ct"]))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{token}")
async def download(token: str) -> FileResponse:
    storage = _local()
    claims = storage.verify(token, "get")
    if claims is None:
        raise AppError(403, "invalid_download_url", "download link is invalid or expired")
    path = storage.path(str(claims["key"]))
    if not path.exists():
        raise not_found("file")
    return FileResponse(
        path,
        media_type=str(claims["ct"]),
        headers={
            "Content-Disposition": content_disposition(str(claims["fn"])),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=300",
        },
    )
