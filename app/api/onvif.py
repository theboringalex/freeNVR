"""ONVIF API endpoints: discovery and camera import."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Query

from app.core.auth import require_api_key
from app.core.onvif_client import discover_cameras, get_device_info, get_stream_uri
from app.models import ONVIFDiscoverResult, ONVIFImportPayload, CameraOut, CameraCreate

router = APIRouter()
Auth = Annotated[str, Depends(require_api_key)]


@router.get("/discover", response_model=list[ONVIFDiscoverResult])
async def discover(_: Auth, timeout: float = Query(5.0)):
    """WS-Discovery broadcast to find ONVIF cameras on the LAN."""
    found = await discover_cameras(timeout=timeout)
    return [
        ONVIFDiscoverResult(
            address=d["address"],
            name=d.get("name"),
            hardware=d.get("hardware"),
            location=d.get("location"),
            rtsp_url=None,
        )
        for d in found
    ]


@router.get("/probe")
async def probe_camera(
    _: Auth,
    host: str = Query(...),
    port: int = Query(8000),
    username: str = Query(""),
    password: str = Query(""),
):
    """Probe an ONVIF camera: returns device info + RTSP URL."""
    try:
        info = await get_device_info(host, port, username, password)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"ONVIF probe failed: {e}")

    rtsp_url = None
    try:
        rtsp_url = await get_stream_uri(host, port, username, password)
    except Exception:
        pass

    return {**info, "rtsp_url": rtsp_url, "host": host, "port": port}


@router.post("/import", response_model=CameraOut, status_code=201)
async def import_camera(payload: ONVIFImportPayload, request: Request, _: Auth):
    """
    Query an ONVIF camera for its RTSP stream URL, then register it in freeNVR.
    """
    try:
        info = await get_device_info(
            payload.onvif_host, payload.onvif_port, payload.username, payload.password
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"ONVIF connection failed: {e}")

    rtsp_url = None
    try:
        rtsp_url = await get_stream_uri(
            payload.onvif_host, payload.onvif_port, payload.username, payload.password
        )
    except Exception:
        pass

    if not rtsp_url:
        raise HTTPException(
            status_code=422,
            detail="Could not retrieve RTSP URL via ONVIF. Set the RTSP URL manually.",
        )

    name = (
        payload.camera_name
        or f"{info.get('manufacturer', '')} {info.get('model', '')}".strip()
        or payload.onvif_host
    )

    cam_payload = CameraCreate(
        name=name,
        rtsp_url=rtsp_url,
        recording_mode=payload.recording_mode,
        detection_mode=payload.detection_mode,
        username=payload.username,
        password=payload.password,
        onvif_host=payload.onvif_host,
        onvif_port=payload.onvif_port,
        onvif_events=payload.onvif_events,
    )

    from app.api.cameras import create_camera
    return await create_camera(cam_payload, request, _)
