"""Pydantic models for mission data."""
from typing import Optional
from pydantic import BaseModel, Field


class WaypointItem(BaseModel):
    """A single item from a QGC .waypoints mission file."""

    index: int
    current: bool
    frame: int
    command: int
    param1: float
    param2: float
    param3: float
    param4: float
    latitude: float
    longitude: float
    altitude: float
    autocontinue: bool


class MissionInfo(BaseModel):
    """Parsed mission summary, computed after loading a .waypoints file."""

    filename: str
    waypoint_count: int
    nav_waypoints: int
    total_distance_m: float
    total_distance_km: float
    estimated_duration_minutes: float
    estimated_battery_percent: float
    min_altitude_m: float
    max_altitude_m: float
    waypoints: list[WaypointItem]


class MissionStatus(BaseModel):
    """Real-time mission execution status."""

    uploaded: bool = False
    waypoint_count: int = 0
    current_waypoint: int = 0
    total_waypoints: int = 0
    progress_percent: float = 0.0
    mission_info: Optional[MissionInfo] = None


class ApiResponse(BaseModel):
    """Uniform API response envelope."""

    success: bool
    message: str
    data: Optional[dict] = None


class UploadResponse(BaseModel):
    """Response returned after a mission file upload."""

    success: bool
    message: str
    mission_info: Optional[MissionInfo] = None
    uploaded_to_drone: bool = False
