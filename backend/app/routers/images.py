import asyncio
import json
import logging

from docker.errors import APIError, ImageNotFound
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.models.docker import (
    BuildRequest,
    ImageInfo,
    PullRequest,
    RegistryAuth,
)
from app.services.docker_svc import docker_service

logger = logging.getLogger("spark-manager.images")
router = APIRouter()


@router.get("/", response_model=list[ImageInfo])
async def list_images():
    return await asyncio.to_thread(docker_service.list_images)


@router.post("/pull")
async def pull_image(req: PullRequest):
    auth_config = None
    if req.registry:
        auth_config = {"serveraddress": req.registry}

    def stream():
        try:
            for event in docker_service.pull_image(
                req.image, tag=req.tag, auth_config=auth_config,
            ):
                yield json.dumps(event) + "\n"
        except APIError as e:
            yield json.dumps({"error": str(e)}) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@router.post("/build")
async def build_image(req: BuildRequest):
    def stream():
        try:
            for event in docker_service.build_image(
                path=req.context_path, tag=req.tag, dockerfile=req.dockerfile,
            ):
                yield json.dumps(event) + "\n"
        except APIError as e:
            yield json.dumps({"error": str(e)}) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@router.delete("/{image_id}")
async def remove_image(image_id: str, force: bool = Query(False)):
    try:
        await asyncio.to_thread(docker_service.remove_image, image_id, force)
    except ImageNotFound:
        raise HTTPException(status_code=404, detail="Image not found")
    except APIError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"message": f"Image '{image_id}' removed"}


@router.post("/prune")
async def prune_images():
    result = await asyncio.to_thread(docker_service.prune_images)
    return {
        "images_deleted": result.get("ImagesDeleted") or [],
        "space_reclaimed": result.get("SpaceReclaimed", 0),
    }


@router.post("/registries")
async def login_registry(auth: RegistryAuth):
    try:
        result = await asyncio.to_thread(
            docker_service.login_registry,
            auth.server,
            auth.username,
            auth.password,
        )
    except APIError as e:
        raise HTTPException(status_code=401, detail=str(e))
    return {"message": "Login succeeded", "status": result.get("Status", "")}
