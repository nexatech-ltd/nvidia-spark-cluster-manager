import logging
import mimetypes
import os

from fastapi import APIRouter, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.config import settings
from app.models.files import ChmodRequest, FileEntry, MkdirRequest, RenameRequest
from app.services.file_svc import file_service

logger = logging.getLogger("spark-manager.files")
router = APIRouter()


# ── List Directory ───────────────────────────────────────────────────────────


@router.get("/{node}/list", response_model=list[FileEntry])
async def list_directory(
    node: str,
    path: str = Query(default=None),
):
    if path is None:
        path = settings.nfs_roots[0] if settings.nfs_roots else "/"
    try:
        entries = await file_service.list_dir(node, path)
        return [FileEntry(**e) for e in entries]
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Directory not found: {path}")
    except Exception as e:
        logger.exception("Error listing directory")
        raise HTTPException(status_code=500, detail=str(e))


# ── Download File ────────────────────────────────────────────────────────────


@router.get("/{node}/download")
async def download_file(node: str, path: str = Query(...)):
    try:
        result = await file_service.download_file(node, path)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    except Exception as e:
        logger.exception("Error downloading file")
        raise HTTPException(status_code=500, detail=str(e))

    filename = os.path.basename(path)
    content_type, _ = mimetypes.guess_type(filename)
    if content_type is None:
        content_type = "application/octet-stream"

    if isinstance(result, str):
        import aiofiles

        async def _stream_local():
            async with aiofiles.open(result, "rb") as f:
                while True:
                    chunk = await f.read(64 * 1024)
                    if not chunk:
                        break
                    yield chunk

        return StreamingResponse(
            _stream_local(),
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )
    else:
        return StreamingResponse(
            iter([result]),
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )


# ── Upload Files ─────────────────────────────────────────────────────────────


@router.post("/{node}/upload")
async def upload_files(
    node: str,
    files: list[UploadFile],
    path: str = Query(...),
):
    results = []
    errors = []
    for f in files:
        if not f.filename:
            continue
        try:
            data = await f.read()
            result = await file_service.upload_file(node, path, data, f.filename)
            results.append(result)
        except ValueError as e:
            errors.append({"file": f.filename, "error": str(e)})
        except Exception as e:
            errors.append({"file": f.filename, "error": str(e)})
    if errors and not results:
        raise HTTPException(status_code=400, detail=errors)
    return {"uploaded": results, "errors": errors}


# ── Create Directory ─────────────────────────────────────────────────────────


@router.post("/{node}/mkdir")
async def make_directory(node: str, body: MkdirRequest):
    try:
        return await file_service.mkdir(node, body.path)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Change Permissions ───────────────────────────────────────────────────────


@router.put("/{node}/chmod")
async def change_permissions(node: str, body: ChmodRequest):
    try:
        return await file_service.chmod(node, body.path, body.mode, body.recursive)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Rename / Move ────────────────────────────────────────────────────────────


@router.put("/{node}/rename")
async def rename_file(node: str, body: RenameRequest):
    try:
        return await file_service.rename(node, body.old_path, body.new_path)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"File not found: {body.old_path}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Delete ───────────────────────────────────────────────────────────────────


@router.delete("/{node}/delete")
async def delete_file(
    node: str,
    path: str = Query(...),
    recursive: bool = Query(False),
):
    try:
        return await file_service.delete(node, path, recursive)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Stat / Info ──────────────────────────────────────────────────────────────


@router.get("/{node}/stat")
async def get_stat(node: str, path: str = Query(...)):
    try:
        return await file_service.stat(node, path)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
