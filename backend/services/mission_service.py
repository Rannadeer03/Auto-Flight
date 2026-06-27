"""
Mission file management and upload coordination.

Responsibilities:
  • Receive and validate uploaded .waypoints files
  • Store them on disk with sanitised names
  • Parse them into structured MissionInfo
  • Upload parsed waypoints to the Pixhawk via MAVLink
  • Keep the shared DroneState in sync with mission status
"""
import logging
import re
import uuid
from pathlib import Path
from typing import Optional

from config import settings
from mavlink.connection import connection, drone_state
from mavlink.mission_upload import MissionUploader, MissionUploadError
from models.mission import MissionInfo
from parser.waypoint_parser import QGCWaypointParser, WaypointParseError

logger = logging.getLogger(__name__)


class MissionService:
    """Handles the full mission lifecycle from file upload to Pixhawk execution."""

    def __init__(self) -> None:
        self._parser = QGCWaypointParser()
        self._uploader = MissionUploader(connection)
        self._current_mission: Optional[MissionInfo] = None
        settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    # ── Public API ─────────────────────────────────────────────────────────────

    def process_upload(self, filename: str, data: bytes) -> dict:
        """Parse, save, and (if connected) upload a mission file.

        Returns a dict with keys:
          mission_info        — parsed MissionInfo
          uploaded_to_drone   — bool
          saved_path          — str
        """
        self._validate_file_meta(filename, len(data))
        safe_name = self._sanitise_filename(filename)

        # Parse & validate
        mission_info = self._parser.parse_bytes(data, safe_name)

        # Save to disk
        save_path = settings.UPLOAD_DIR / f"{uuid.uuid4().hex[:8]}_{safe_name}"
        save_path.write_bytes(data)
        logger.info("Mission file saved: %s (%d waypoints).", save_path.name, mission_info.waypoint_count)

        self._current_mission = mission_info
        uploaded = False

        if drone_state.connected:
            logger.info("Uploading mission to Pixhawk.")
            self._uploader.clear_mission()
            self._uploader.upload_waypoints(mission_info.waypoints)
            drone_state.update(
                mission_uploaded=True,
                waypoint_count=mission_info.waypoint_count,
                current_waypoint=0,
            )
            uploaded = True
            logger.info(
                "Mission uploaded: %d items, %.2f km, ~%.0f min.",
                mission_info.waypoint_count,
                mission_info.total_distance_km,
                mission_info.estimated_duration_minutes,
            )
        else:
            logger.info("Drone not connected — mission parsed but not sent to vehicle.")

        return {
            "mission_info": mission_info,
            "uploaded_to_drone": uploaded,
            "saved_path": str(save_path),
        }

    def upload_current_to_drone(self) -> None:
        """Push the already-parsed mission to the Pixhawk (used after late connect)."""
        if not self._current_mission:
            raise RuntimeError("No mission loaded. Upload a .waypoints file first.")
        if not drone_state.connected:
            raise RuntimeError("Not connected to Pixhawk.")
        self._uploader.clear_mission()
        self._uploader.upload_waypoints(self._current_mission.waypoints)
        drone_state.update(
            mission_uploaded=True,
            waypoint_count=self._current_mission.waypoint_count,
            current_waypoint=0,
        )
        logger.info("Pending mission uploaded to drone (%d items).", self._current_mission.waypoint_count)

    def clear_mission(self) -> None:
        """Clear mission from vehicle and reset local state."""
        if drone_state.connected:
            self._uploader.clear_mission()
        drone_state.update(mission_uploaded=False, waypoint_count=0, current_waypoint=0)
        self._current_mission = None
        logger.info("Mission cleared.")

    @property
    def current_mission(self) -> Optional[MissionInfo]:
        return self._current_mission

    # ── Internal ───────────────────────────────────────────────────────────────

    def _validate_file_meta(self, filename: str, size: int) -> None:
        ext = Path(filename).suffix.lower()
        if ext not in settings.ALLOWED_EXTENSIONS:
            raise WaypointParseError(
                f"File type '{ext}' not accepted. Only {', '.join(settings.ALLOWED_EXTENSIONS)} files are allowed."
            )
        if size > settings.MAX_UPLOAD_BYTES:
            raise WaypointParseError(
                f"File size {size // 1024} KB exceeds the {settings.MAX_UPLOAD_BYTES // 1024 // 1024} MB limit."
            )
        if size == 0:
            raise WaypointParseError("Uploaded file is empty.")

    @staticmethod
    def _sanitise_filename(filename: str) -> str:
        """Strip path components and remove dangerous characters."""
        name = Path(filename).name
        safe = re.sub(r"[^\w\-.]", "_", name)
        safe = safe[:128]
        if not safe.lower().endswith(".waypoints"):
            safe += ".waypoints"
        return safe


mission_service = MissionService()
