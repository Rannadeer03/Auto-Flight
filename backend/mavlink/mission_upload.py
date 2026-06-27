"""
MAVLink mission upload protocol implementation.

Implements the full GCS→Vehicle handshake:
  GCS sends MISSION_COUNT
  Vehicle sends MISSION_REQUEST_INT (or MISSION_REQUEST) per item
  GCS sends MISSION_ITEM_INT for each requested index
  Vehicle sends MISSION_ACK
"""
import logging
import time
from pymavlink import mavutil
from mavlink.connection import MAVLinkConnection
from models.mission import WaypointItem

logger = logging.getLogger(__name__)

_UPLOAD_TOTAL_TIMEOUT = 60.0  # seconds — covers 1000-waypoint missions
_ITEM_REQUEST_TIMEOUT = 5.0   # seconds per item request


class MissionUploadError(RuntimeError):
    """Raised when mission upload fails or times out."""


class MissionUploader:
    """Implements the MAVLink mission upload and clear protocols."""

    def __init__(self, conn: MAVLinkConnection) -> None:
        self._conn = conn

    def clear_mission(self) -> bool:
        """Remove all stored mission items from the vehicle."""
        m = self._require_master()
        logger.info("Clearing vehicle mission.")
        m.mav.mission_clear_all_send(
            m.target_system,
            m.target_component,
            mavutil.mavlink.MAV_MISSION_TYPE_MISSION,
        )
        ack = m.recv_match(type="MISSION_ACK", blocking=True, timeout=5.0)
        if ack and ack.type == mavutil.mavlink.MAV_MISSION_ACCEPTED:
            logger.info("Mission cleared.")
            return True
        logger.warning("Mission clear timed out or not accepted (ack=%s).", ack)
        return False

    def upload_waypoints(self, waypoints: list[WaypointItem]) -> bool:
        """Upload a waypoint list to the vehicle using the MAVLink handshake.

        Returns True on success, raises MissionUploadError on protocol failure.
        """
        m = self._require_master()
        count = len(waypoints)
        if count == 0:
            raise MissionUploadError("Cannot upload an empty mission.")

        logger.info("Uploading %d mission items.", count)

        m.mav.mission_count_send(
            m.target_system,
            m.target_component,
            count,
            mavutil.mavlink.MAV_MISSION_TYPE_MISSION,
        )

        items_confirmed = 0
        deadline = time.monotonic() + _UPLOAD_TOTAL_TIMEOUT

        while items_confirmed < count and time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            msg = m.recv_match(
                type=["MISSION_REQUEST_INT", "MISSION_REQUEST", "MISSION_ACK"],
                blocking=True,
                timeout=min(_ITEM_REQUEST_TIMEOUT, remaining),
            )

            if msg is None:
                raise MissionUploadError(
                    f"Vehicle stopped requesting items after {items_confirmed}/{count} sent."
                )

            msg_type = msg.get_type()

            if msg_type == "MISSION_ACK":
                if msg.type == mavutil.mavlink.MAV_MISSION_ACCEPTED:
                    logger.info("Mission upload complete — %d items accepted.", count)
                    return True
                raise MissionUploadError(
                    f"Vehicle rejected mission. MISSION_ACK type={msg.type}."
                )

            # MISSION_REQUEST_INT or MISSION_REQUEST
            seq = msg.seq
            if seq >= count:
                raise MissionUploadError(
                    f"Vehicle requested out-of-range item seq={seq} (count={count})."
                )

            use_int = msg_type == "MISSION_REQUEST_INT"
            self._send_item(m, waypoints[seq], seq, use_int=use_int)
            items_confirmed = seq + 1
            logger.debug("Sent item %d/%d command=%d.", seq + 1, count, waypoints[seq].command)

        # Wait for the final ACK after all items are sent
        ack = m.recv_match(type="MISSION_ACK", blocking=True, timeout=5.0)
        if ack and ack.type == mavutil.mavlink.MAV_MISSION_ACCEPTED:
            logger.info("Mission upload confirmed (%d items).", count)
            return True

        raise MissionUploadError("Timed out waiting for final MISSION_ACK.")

    # ── Internal ───────────────────────────────────────────────────────────────

    def _send_item(
        self,
        master: mavutil.mavfile,
        wp: WaypointItem,
        seq: int,
        use_int: bool,
    ) -> None:
        if use_int:
            master.mav.mission_item_int_send(
                master.target_system,
                master.target_component,
                seq,
                wp.frame,
                wp.command,
                1 if wp.current else 0,
                int(wp.autocontinue),
                wp.param1,
                wp.param2,
                wp.param3,
                wp.param4,
                int(wp.latitude * 1e7),
                int(wp.longitude * 1e7),
                wp.altitude,
                mavutil.mavlink.MAV_MISSION_TYPE_MISSION,
            )
        else:
            master.mav.mission_item_send(
                master.target_system,
                master.target_component,
                seq,
                wp.frame,
                wp.command,
                1 if wp.current else 0,
                int(wp.autocontinue),
                wp.param1,
                wp.param2,
                wp.param3,
                wp.param4,
                wp.latitude,
                wp.longitude,
                wp.altitude,
                mavutil.mavlink.MAV_MISSION_TYPE_MISSION,
            )

    def _require_master(self) -> mavutil.mavfile:
        if not self._conn.master:
            raise RuntimeError("Not connected to Pixhawk.")
        return self._conn.master
