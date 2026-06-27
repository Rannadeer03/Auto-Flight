"""
Connection lifecycle service.

Thin orchestration layer between the API route and the MAVLink connection.
Centralises connection state so routes never import pymavlink directly.
"""
import logging
from mavlink.connection import connection, drone_state, DroneState
from config import settings

logger = logging.getLogger(__name__)


class ConnectionService:
    """Manages connect / disconnect lifecycle."""

    def connect(self) -> None:
        """Open the MAVLink link to the Pixhawk.

        Raises:
            RuntimeError: already connected.
            ConnectionError: serial port could not be opened.
            TimeoutError: heartbeat did not arrive in time.
        """
        if drone_state.connected:
            raise RuntimeError("Already connected to the Pixhawk.")
        connection.connect(
            port=settings.MAVLINK_PORT,
            baud=settings.MAVLINK_BAUD,
            timeout=settings.MAVLINK_TIMEOUT,
        )
        logger.info(
            "Connected to Pixhawk on %s @ %d baud.",
            settings.MAVLINK_PORT, settings.MAVLINK_BAUD,
        )

    def disconnect(self) -> None:
        """Close the MAVLink link."""
        connection.disconnect()
        logger.info("Disconnected from Pixhawk.")

    @property
    def state(self) -> DroneState:
        return drone_state


connection_service = ConnectionService()
