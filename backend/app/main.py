import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings

logger = logging.getLogger("spark-manager")
logging.basicConfig(level=logging.INFO)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Spark Cluster Manager starting up")
    logger.info(
        "Cluster nodes: %s (%s), %s (%s)",
        settings.node1_hostname,
        settings.node1_ip,
        settings.node2_hostname,
        settings.node2_ip,
    )
    yield
    logger.info("Spark Cluster Manager shutting down")


app = FastAPI(
    title="Spark Cluster Manager",
    version="1.5.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from .routers import (  # noqa: E402
    docker,
    files,
    images,
    network,
    slurm,
    storage,
    system,
    traefik,
    vms,
    vnc,
)

app.include_router(docker.router, prefix="/api/docker", tags=["docker"])
app.include_router(images.router, prefix="/api/images", tags=["images"])
app.include_router(vms.router, prefix="/api/vms", tags=["vms"])
app.include_router(vnc.router, prefix="/api/vnc", tags=["vnc"])
app.include_router(slurm.router, prefix="/api/slurm", tags=["slurm"])
app.include_router(network.router, prefix="/api/network", tags=["network"])
app.include_router(storage.router, prefix="/api/storage", tags=["storage"])
app.include_router(files.router, prefix="/api/files", tags=["files"])
app.include_router(system.router, prefix="/api/system", tags=["system"])
app.include_router(traefik.router, prefix="/api/traefik", tags=["traefik"])

from .auth import (  # noqa: E402
    LoginRequest,
    TokenResponse,
    authenticate_user,
    create_access_token,
)


@app.post("/api/auth/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    user = authenticate_user(request.username, request.password)
    if not user:
        return JSONResponse(
            status_code=401, content={"detail": "Invalid credentials"}
        )
    token = create_access_token(data={"sub": user.username})
    return TokenResponse(access_token=token)


@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
        "version": "1.5.0",
        "nodes": [settings.node1_hostname, settings.node2_hostname],
    }


if FRONTEND_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        if full_path.startswith("api/") or full_path.startswith("ws/"):
            return JSONResponse(
                status_code=404,
                content={"detail": f"API endpoint '/{full_path}' not found"},
            )
        file_path = FRONTEND_DIR / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_DIR / "index.html")
