"""API routes: /connect and /disconnect."""
import logging
from fastapi import APIRouter
from models.mission import ApiResponse
from services.connection_service import connection_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["connection"])


@router.post("/connect", response_model=ApiResponse)
async def connect_drone() -> ApiResponse:
    """Open MAVLink connection to the Pixhawk."""
    try:
        connection_service.connect()
        return ApiResponse(success=True, message="Connected to Pixhawk successfully.")
    except RuntimeError as exc:
        return ApiResponse(success=False, message=str(exc))
    except ConnectionError as exc:
        logger.error("Connection failed: %s", exc)
        return ApiResponse(success=False, message=f"Connection failed: {exc}")
    except TimeoutError as exc:
        logger.error("Heartbeat timeout: %s", exc)
        return ApiResponse(success=False, message=f"Timeout: {exc}")
    except Exception as exc:
        logger.exception("Unexpected error during connect.")
        return ApiResponse(success=False, message=f"Unexpected error: {exc}")


@router.post("/disconnect", response_model=ApiResponse)
async def disconnect_drone() -> ApiResponse:
    """Close the MAVLink connection."""
    try:
        connection_service.disconnect()
        return ApiResponse(success=True, message="Disconnected from Pixhawk.")
    except Exception as exc:
        logger.exception("Error during disconnect.")
        return ApiResponse(success=False, message=f"Disconnect error: {exc}")
