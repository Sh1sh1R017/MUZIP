"""
main.py - FastAPI Application Entry Point
Exposes REST APIs, WebSocket progress engine, background garbage collection,
and serves the Single Page Application UI dashboard.
"""

import asyncio
from contextlib import asynccontextmanager
import logging
import os
import shutil
import tempfile
from typing import Any, Dict, List, Optional
import psutil
from fastapi import (
    BackgroundTasks,
    FastAPI,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel
import uvicorn

from converter import (
    download_single_track_sync,
    download_track_async,
    extract_url_info,
    sanitize_filename,
)
from zipper import stream_playlist_as_zip

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ACTIVE_JOBS = 0


class InfoRequest(BaseModel):
    url: str


class DownloadSingleRequest(BaseModel):
    url: str
    client_id: Optional[str] = None


class DownloadPlaylistRequest(BaseModel):
    url: str
    client_id: Optional[str] = None


class ConnectionManager:
    """Manages active WebSocket connections for live client progress updates."""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, client_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[client_id] = websocket
        logger.info("Client connected to WS: %s", client_id)

    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            logger.info("Client disconnected from WS: %s", client_id)

    async def send_telemetry(self, client_id: str, data: Dict[str, Any]):
        if client_id and client_id in self.active_connections:
            try:
                await self.active_connections[client_id].send_json(data)
            except Exception as e:
                logger.warning("Error sending WS telemetry to %s: %s", client_id, e)


manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting YouTube to MP3 & Instant Playlist Zipper Engine...")
    yield
    logger.info("Shutting down engine...")


app = FastAPI(
    title="YouTube to MP3 & Instant Playlist Zipper API",
    description="Production-Grade Ultra-Fast Audio Converter & Dynamic Zip Streamer",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def cleanup_temp_dir(dir_path: str):
    """Background task to purge temporary audio files from RAM/Disk."""
    if os.path.exists(dir_path):
        try:
            shutil.rmtree(dir_path)
            logger.info("Purged temporary directory: %s", dir_path)
        except Exception as e:
            logger.error("Failed to purge temp directory %s: %s", dir_path, e)


@app.get("/health", summary="System Health & Status Checklist")
async def health_check():
    """Returns system health, RAM usage percentage, active job count, and ffmpeg status."""
    mem = psutil.virtual_memory()
    ffmpeg_path = shutil.which("ffmpeg")
    ffmpeg_available = ffmpeg_path is not None

    return {
        "status": "healthy" if ffmpeg_available else "degraded",
        "ram_usage_pct": mem.percent,
        "ram_used_mb": round(mem.used / (1024 * 1024), 2),
        "ram_total_mb": round(mem.total / (1024 * 1024), 2),
        "active_jobs": ACTIVE_JOBS,
        "ffmpeg": {
            "installed": ffmpeg_available,
            "binary_path": ffmpeg_path or "Not Found in PATH",
        },
    }


@app.post("/api/v1/info", summary="Extract URL Metadata & Track List")
async def get_info(req: InfoRequest):
    """Accepts a YouTube video or playlist URL and returns structured JSON metadata dynamically."""
    if not req.url or not req.url.strip():
        raise HTTPException(status_code=400, detail="URL cannot be empty.")
    
    try:
        info_data = await extract_url_info(req.url.strip())
        return {"success": True, "data": info_data}
    except Exception as e:
        logger.error("Error extracting metadata: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/v1/download/single", summary="Download Single Track as 320kbps MP3")
async def download_single(req: DownloadSingleRequest, background_tasks: BackgroundTasks):
    """Converts a single YouTube video to 320kbps MP3 dynamically."""
    global ACTIVE_JOBS
    ACTIVE_JOBS += 1

    temp_dir = tempfile.mkdtemp(prefix="yt_single_")

    try:
        def ws_callback(data):
            if req.client_id:
                asyncio.run_coroutine_threadsafe(
                    manager.send_telemetry(req.client_id, data),
                    asyncio.get_event_loop()
                )

        meta = await extract_url_info(req.url)
        real_title = meta.get("title", "Audio Track")

        mp3_path = await download_track_async(
            url=req.url,
            output_dir=temp_dir,
            filename_prefix="",
            track_index=1,
            total_tracks=1,
            progress_callback=ws_callback if req.client_id else None,
            track_title_hint=real_title,
        )

        if not os.path.exists(mp3_path):
            raise HTTPException(status_code=500, detail="MP3 encoding failed.")

        filename = os.path.basename(mp3_path)
        background_tasks.add_task(cleanup_temp_dir, temp_dir)

        if req.client_id:
            await manager.send_telemetry(req.client_id, {
                "type": "PROGRESS_UPDATE",
                "payload": {
                    "current_track_index": 1,
                    "total_tracks": 1,
                    "track_title": filename.replace(".mp3", ""),
                    "status": "COMPLETE",
                    "track_progress_pct": 100.0,
                    "overall_progress_pct": 100.0,
                    "speed_mbps": 0.0,
                    "eta_seconds": 0,
                }
            })

        return FileResponse(
            path=mp3_path,
            filename=filename,
            media_type="audio/mpeg",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        cleanup_temp_dir(temp_dir)
        logger.error("Download single track error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        ACTIVE_JOBS = max(0, ACTIVE_JOBS - 1)


@app.post("/api/v1/download/playlist", summary="Stream Playlist as Dynamic ZIP")
async def download_playlist(req: DownloadPlaylistRequest, background_tasks: BackgroundTasks):
    """Downloads all tracks in a playlist dynamically and streams a ZIP archive."""
    global ACTIVE_JOBS
    ACTIVE_JOBS += 1

    temp_dir = tempfile.mkdtemp(prefix="yt_playlist_")

    try:
        meta = await extract_url_info(req.url)
        tracks = meta.get("tracks", [])
        total_tracks = len(tracks)

        if total_tracks == 0:
            cleanup_temp_dir(temp_dir)
            raise HTTPException(status_code=400, detail="No tracks found in playlist.")

        def send_progress_sync(payload_data):
            if req.client_id:
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.run_coroutine_threadsafe(
                            manager.send_telemetry(req.client_id, payload_data),
                            loop
                        )
                except Exception as ex:
                    logger.warning("WS progress broadcast exception: %s", ex)

        downloaded_files: List[tuple[str, str]] = []
        semaphore = asyncio.Semaphore(4)

        async def _download_item(track: Dict[str, Any]):
            async with semaphore:
                idx = track["index"]
                track_title = track["title"]
                track_url = track["url"]
                prefix = f"{idx:02d} - "

                def cb(data):
                    send_progress_sync(data)

                try:
                    path = await download_track_async(
                        url=track_url,
                        output_dir=temp_dir,
                        filename_prefix=prefix,
                        track_index=idx,
                        total_tracks=total_tracks,
                        progress_callback=cb,
                        track_title_hint=track_title,
                    )
                    arc_name = f"{prefix}{sanitize_filename(track_title)}.mp3"
                    downloaded_files.append((path, arc_name))
                except Exception as err:
                    logger.error("Error downloading track %s: %s", track_title, err)

        tasks = [_download_item(t) for t in tracks]
        await asyncio.gather(*tasks)

        if not downloaded_files:
            cleanup_temp_dir(temp_dir)
            raise HTTPException(status_code=500, detail="Failed to download playlist tracks.")

        playlist_title = sanitize_filename(meta.get("title", "playlist"))
        zip_filename = f"{playlist_title}.zip"

        background_tasks.add_task(cleanup_temp_dir, temp_dir)

        if req.client_id:
            await manager.send_telemetry(req.client_id, {
                "type": "PROGRESS_UPDATE",
                "payload": {
                    "current_track_index": total_tracks,
                    "total_tracks": total_tracks,
                    "track_title": "All Tracks Complete",
                    "status": "COMPLETE",
                    "track_progress_pct": 100.0,
                    "overall_progress_pct": 100.0,
                    "speed_mbps": 0.0,
                    "eta_seconds": 0,
                }
            })

        return StreamingResponse(
            stream_playlist_as_zip(downloaded_files),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{zip_filename}"'}
        )

    except Exception as e:
        cleanup_temp_dir(temp_dir)
        logger.error("Download playlist error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        ACTIVE_JOBS = max(0, ACTIVE_JOBS - 1)


@app.websocket("/ws/progress/{client_id}")
async def websocket_progress_endpoint(websocket: WebSocket, client_id: str):
    """Bidirectional WebSocket connection for pushing live execution telemetry."""
    await manager.connect(client_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(client_id)
    except Exception as e:
        logger.warning("WebSocket connection error for %s: %s", client_id, e)
        manager.disconnect(client_id)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
