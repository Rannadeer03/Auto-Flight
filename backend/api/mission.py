"""API routes: /upload, /mission, /clear."""
import logging
from fastapi import APIRouter, File, HTTPException, UploadFile
from models.mission import ApiResponse, MissionStatus, UploadResponse
from mavlink.connection import drone_state
from parser.waypoint_parser import WaypointParseError
from services.mission_service import mission_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["mission"])


@router.post("/upload", response_model=UploadResponse)
async def upload_mission(file: UploadFile = File(...)) -> UploadResponse:
    """Accept a .waypoints file, parse it, and upload it to the Pixhawk if connected."""
    if file.filename is None or file.filename == "":
        raise HTTPException(status_code=400, detail="No filename provided.")

    data = await file.read()

    try:
        result = mission_service.process_upload(file.filename, data)
    except WaypointParseError as exc:
        logger.warning("Mission parse error: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        logger.error("Mission upload error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        logger.exception("Unexpected error during mission upload.")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {exc}")

    msg = "Mission parsed and uploaded to vehicle." if result["uploaded_to_drone"] else \
          "Mission parsed and saved. Connect to drone to upload to vehicle."

    return UploadResponse(
        success=True,
        message=msg,
        mission_info=result["mission_info"],
        uploaded_to_drone=result["uploaded_to_drone"],
    )


@router.get("/mission", response_model=MissionStatus)
async def get_mission_status() -> MissionStatus:
    """Return current mission status."""
    current = mission_service.current_mission
    s = drone_state
    total = s.waypoint_count
    current_wp = s.current_waypoint

    return MissionStatus(
        uploaded=s.mission_uploaded,
        waypoint_count=total,
        current_waypoint=current_wp,
        total_waypoints=total,
        progress_percent=round((current_wp / total * 100) if total > 0 else 0.0, 1),
        mission_info=current,
    )


@router.post("/clear", response_model=ApiResponse)
async def clear_mission() -> ApiResponse:
    """Remove the mission from the vehicle and reset local state."""
    try:
        mission_service.clear_mission()
        return ApiResponse(success=True, message="Mission cleared.")
    except Exception as exc:
        logger.exception("Error clearing mission.")
        return ApiResponse(success=False, message=f"Clear failed: {exc}")
