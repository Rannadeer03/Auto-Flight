"""
MAVLink command senders.

Wraps all COMMAND_LONG / mode-change calls so the rest of the codebase
never touches pymavlink directly.
"""
import logging
import time
from pymavlink import mavutil
from mavlink.connection import MAVLinkConnection, ARDUPILOT_MODES

logger = logging.getLogger(__name__)

_ACK_TIMEOUT = 5.0   # seconds to wait for COMMAND_ACK
_MODE_TIMEOUT = 5.0  # seconds to wait for flight mode to change


class MAVLinkCommands:
    """High-level flight command interface."""

    def __init__(self, conn: MAVLinkConnection) -> None:
        self._conn = conn

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _master(self) -> mavutil.mavfile:
        if not self._conn.master:
            raise RuntimeError("Not connected to Pixhawk.")
        return self._conn.master

    def _send_command_long(
        self,
        command: int,
        p1: float = 0, p2: float = 0, p3: float = 0,
        p4: float = 0, p5: float = 0, p6: float = 0, p7: float = 0,
        confirmation: int = 0,
    ) -> bool:
        m = self._master()
        m.mav.command_long_send(
            m.target_system,
            m.target_component,
            command,
            confirmation,
            p1, p2, p3, p4, p5, p6, p7,
        )
        return self._await_ack(command)

    def _await_ack(self, command: int) -> bool:
        m = self._master()
        deadline = time.monotonic() + _ACK_TIMEOUT
        while time.monotonic() < deadline:
            ack = m.recv_match(type="COMMAND_ACK", blocking=True, timeout=0.5)
            if ack is None:
                continue
            if ack.command != command:
                continue
            if ack.result == mavutil.mavlink.MAV_RESULT_ACCEPTED:
                return True
            result_enum = mavutil.mavlink.enums.get("MAV_RESULT", {})
            name = result_enum.get(ack.result, type("", (), {"name": str(ack.result)})()).name
            logger.warning("Command 0x%04X rejected: %s", command, name)
            return False
        logger.warning("Command 0x%04X — no ACK within %.1fs.", command, _ACK_TIMEOUT)
        return False

    def _set_mode_raw(self, mode_name: str) -> bool:
        """Switch to an ArduPilot named mode and wait for telemetry confirmation."""
        mode_id = ARDUPILOT_MODES.get(mode_name.upper())
        if mode_id is None:
            raise ValueError(f"Unknown ArduPilot mode: '{mode_name}'.")
        m = self._master()
        logger.info("Setting mode → %s (id=%d).", mode_name, mode_id)
        m.set_mode(mode_id)

        deadline = time.monotonic() + _MODE_TIMEOUT
        while time.monotonic() < deadline:
            if self._conn.state.flight_mode.upper() == mode_name.upper():
                logger.info("Mode confirmed: %s.", mode_name)
                return True
            time.sleep(0.1)

        logger.warning("Mode change to %s timed out (current=%s).", mode_name, self._conn.state.flight_mode)
        return False

    # ── Public command API ─────────────────────────────────────────────────────

    def arm(self) -> bool:
        logger.info("Sending ARM command.")
        return self._send_command_long(
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
            p1=1,   # 1 = arm
            p2=0,
        )

    def disarm(self, force: bool = False) -> bool:
        logger.info("Sending DISARM command (force=%s).", force)
        return self._send_command_long(
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
            p1=0,
            # ArduPilot magic number for force-disarm in flight
            p2=21196 if force else 0,
        )

    def start_auto(self) -> bool:
        """Switch to AUTO mode to begin executing the uploaded mission."""
        logger.info("Starting AUTO mission.")
        return self._set_mode_raw("AUTO")

    def pause(self) -> bool:
        """Pause mission by switching to LOITER (holds position)."""
        logger.info("Pausing mission → LOITER.")
        return self._set_mode_raw("LOITER")

    def resume(self) -> bool:
        """Resume paused mission by switching back to AUTO."""
        logger.info("Resuming mission → AUTO.")
        return self._set_mode_raw("AUTO")

    def rtl(self) -> bool:
        """Return to launch."""
        logger.info("Initiating RTL.")
        return self._set_mode_raw("RTL")

    def land(self) -> bool:
        """Land in place."""
        logger.info("Initiating LAND.")
        return self._set_mode_raw("LAND")

    def emergency_stop(self) -> bool:
        """Force-disarm the drone immediately, regardless of flight state."""
        logger.critical("EMERGENCY STOP executed.")
        return self.disarm(force=True)

    def set_home_current(self) -> bool:
        """Set home position to current GPS location."""
        return self._send_command_long(
            mavutil.mavlink.MAV_CMD_DO_SET_HOME,
            p1=1,  # use current position
        )
