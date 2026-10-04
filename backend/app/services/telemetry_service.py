"""
GT7 Telemetry Service — auto-discovery via UDP broadcast heartbeat

NOT decoded yet, on purpose: steering wheel rotation, sway/heave/surge
(accelerometers) and per-wheel surface. The docs confirm these exist in
packet formats B/~/C but don't publish their byte offsets.
"""

import asyncio
import logging
import socket
import struct
import time
from typing import Callable, Awaitable, Optional

from Crypto.Cipher import Salsa20

from app.models.telemetry import TelemetryFrame, ConnectionStatus
from app.core.config import settings

logger = logging.getLogger(__name__)

GT7_MAGIC = 0x47375330
KEY = b'Simulator Interface Packet GT7 ver 0.0'

# Packet format -> (datagram size, Salsa20 nonce XOR constant)
# Source: docs.gt7-datalogger.com/internals/telemetry-capture/
FORMAT_INFO = {
    "A": (296, 0xDEADBEAF),   
    "B": (316, 0xDEADBEEF),
    "~": (344, 0x55FABB4F),
    "C": (368, 0xDEADBEEF),
}
SIZE_TO_XOR = {size: xor for size, xor in FORMAT_INFO.values()}
SIZE_TO_FORMAT = {size: fmt for fmt, (size, _) in FORMAT_INFO.items()}

# NOTE: fuel_capacity moved here from 0xA8 (its previous location) to 0x48.
# 0xA8 collided with the new wheel_speed_fr offset from the docs, and 0x48 —
# right after fuel_level.
_OFF = {
    "magic":            0x0,
    "rpm":              0x3C,
    "fuel_level":       0x44,
    "fuel_capacity":    0x48,   # moved from 0xA8 — see note above, that offset collided with wheel_speed_fr
    "speed":            0x4C,
    "boost":            0x50,   # docs — raw, subtract 1.0 for bar
    "oil_pressure":     0x54,   # docs — bar
    "water_temp":       0x58,   # docs — °C
    "oil_temp":         0x5C,   # docs — °C
    "tyre_temp_fl":     0x64,
    "tyre_temp_fr":     0x68,
    "tyre_temp_rl":     0x6C,
    "tyre_temp_rr":     0x70,
    "lap_count":        0x74,
    "laps_in_race":     0x78,
    "best_lap_ms":      0x7C,
    "last_lap_ms":      0x80,
    "rpm_alert_min":    0x88,   # docs — shift-light thresholds, uint16 pair
    "rpm_alert_max":    0x8A,   # docs
    "flags":            0x8E,
    "gear":             0x90,   # low nibble = current, high nibble = suggested
    "throttle":         0x91,
    "wheel_speed_fl":   0xA4,   # docs — rad/s, signed
    "wheel_speed_fr":   0xA8,
    "wheel_speed_rl":   0xAC,
    "wheel_speed_rr":   0xB0,
    "tire_radius_fl":   0xB4,   # docs — m
    "tire_radius_fr":   0xB8,
    "tire_radius_rl":   0xBC,
    "tire_radius_rr":   0xC0,
    "sus_fl":           0xC4,   # docs — m, × 1000 for mm
    "sus_fr":           0xC8,
    "sus_rl":           0xCC,
    "sus_rr":           0xD0,
    "brake":            0xF3,
    "current_lap_ms":   0x98,
    "car_id":           0x124,
}

# Flags bitmask (0x8E)
FLAG_CAR_ON_TRACK = 1 << 0
FLAG_PAUSED       = 1 << 1
FLAG_LOADING      = 1 << 2
FLAG_IN_GEAR      = 1 << 3
FLAG_HAS_TURBO    = 1 << 4
FLAG_REV_LIMITER  = 1 << 5
FLAG_HANDBRAKE    = 1 << 6
FLAG_ASM_ACTIVE   = 1 << 10
FLAG_TCS_ACTIVE   = 1 << 11


def _decrypt_packet(data: bytes) -> Optional[bytes]:
    if len(data) < 0x48:
        return None
    xor_const = SIZE_TO_XOR.get(len(data))
    candidates = [xor_const] if xor_const else list(SIZE_TO_XOR.values())
    for xor in candidates:
        try:
            oiv = data[0x40:0x44]
            iv1 = int.from_bytes(oiv, byteorder='little')
            iv2 = iv1 ^ xor
            IV = bytearray()
            IV.extend(iv2.to_bytes(4, 'little'))
            IV.extend(iv1.to_bytes(4, 'little'))
            decrypted = Salsa20.new(key=KEY[0:32], nonce=bytes(IV)).decrypt(data)
            if struct.unpack_from("<I", decrypted, 0)[0] == GT7_MAGIC:
                return decrypted
        except Exception as e:
            logger.debug(f"Decrypt attempt failed ({xor:#x}): {e}")
    return None


def _wheel_slip(wheel_rad_s: float, tire_radius_m: float, speed_mps: float) -> float:
    """Slip-ratio proxy: wheel surface speed ÷ car speed. Meaningless below
    1 m/s, so it's pinned to 1.0 there (docs.gt7-datalogger.com)."""
    if speed_mps < 1.0:
        return 1.0
    return abs(wheel_rad_s) * tire_radius_m / speed_mps


def _parse_frame(data: bytes) -> Optional[TelemetryFrame]:
    if len(data) < 0x128:
        return None
    try:
        magic = struct.unpack_from("<I", data, _OFF["magic"])[0]
        if magic != GT7_MAGIC:
            return None

        speed_ms = struct.unpack_from("<f", data, _OFF["speed"])[0]
        rpm      = struct.unpack_from("<f", data, _OFF["rpm"])[0]
        gear_byte = data[_OFF["gear"]]
        gear      = gear_byte & 0x0F
        suggested_gear = (gear_byte >> 4) & 0x0F
        throttle = data[_OFF["throttle"]] / 255.0
        brake    = data[_OFF["brake"]] / 255.0

        lap_count      = struct.unpack_from("<i", data, _OFF["lap_count"])[0]
        laps_in_race   = struct.unpack_from("<i", data, _OFF["laps_in_race"])[0]
        best_lap_ms    = struct.unpack_from("<i", data, _OFF["best_lap_ms"])[0]
        last_lap_ms    = struct.unpack_from("<i", data, _OFF["last_lap_ms"])[0]
        current_lap_ms = struct.unpack_from("<I", data, _OFF["current_lap_ms"])[0]

        fuel_capacity  = struct.unpack_from("<f", data, _OFF["fuel_capacity"])[0]
        fuel_level_raw = struct.unpack_from("<f", data, _OFF["fuel_level"])[0]
        fuel_pct = (fuel_level_raw / fuel_capacity * 100.0) if fuel_capacity > 0 else 0.0

        flags  = struct.unpack_from("<H", data, _OFF["flags"])[0]
        paused = bool(flags & FLAG_PAUSED)
        car_id = struct.unpack_from("<i", data, _OFF["car_id"])[0]

        boost         = struct.unpack_from("<f", data, _OFF["boost"])[0] - 1.0
        oil_pressure  = struct.unpack_from("<f", data, _OFF["oil_pressure"])[0]
        water_temp    = struct.unpack_from("<f", data, _OFF["water_temp"])[0]
        oil_temp      = struct.unpack_from("<f", data, _OFF["oil_temp"])[0]
        rpm_alert_min = struct.unpack_from("<H", data, _OFF["rpm_alert_min"])[0]
        rpm_alert_max = struct.unpack_from("<H", data, _OFF["rpm_alert_max"])[0]

        wheel_speeds = [struct.unpack_from("<f", data, _OFF[f"wheel_speed_{c}"])[0]
                        for c in ("fl", "fr", "rl", "rr")]
        tire_radii   = [struct.unpack_from("<f", data, _OFF[f"tire_radius_{c}"])[0]
                        for c in ("fl", "fr", "rl", "rr")]
        slip_fl, slip_fr, slip_rl, slip_rr = [
            _wheel_slip(ws, tr, speed_ms) for ws, tr in zip(wheel_speeds, tire_radii)
        ]

        sus = {c: struct.unpack_from("<f", data, _OFF[f"sus_{c}"])[0] * 1000.0
               for c in ("fl", "fr", "rl", "rr")}

        return TelemetryFrame(
            speed=round(speed_ms * 3.6, 1),
            rpm=round(rpm, 0),
            gear=gear,
            suggested_gear=suggested_gear if suggested_gear != 15 else None,
            throttle=round(throttle, 3),
            brake=round(brake, 3),
            lap_number=max(0, lap_count),
            lap_time_ms=current_lap_ms,
            last_lap_ms=last_lap_ms,
            best_lap_ms=best_lap_ms,
            total_laps=max(0, laps_in_race),
            fuel_level=round(fuel_pct, 1),
            tyre_temp_fl=round(struct.unpack_from("<f", data, _OFF["tyre_temp_fl"])[0], 1),
            tyre_temp_fr=round(struct.unpack_from("<f", data, _OFF["tyre_temp_fr"])[0], 1),
            tyre_temp_rl=round(struct.unpack_from("<f", data, _OFF["tyre_temp_rl"])[0], 1),
            tyre_temp_rr=round(struct.unpack_from("<f", data, _OFF["tyre_temp_rr"])[0], 1),
            slip_fl=round(slip_fl, 3),
            slip_fr=round(slip_fr, 3),
            slip_rl=round(slip_rl, 3),
            slip_rr=round(slip_rr, 3),
            sus_fl=round(sus["fl"], 1),
            sus_fr=round(sus["fr"], 1),
            sus_rl=round(sus["rl"], 1),
            sus_rr=round(sus["rr"], 1),
            boost=round(boost, 3),
            water_temp=round(water_temp, 1),
            oil_temp=round(oil_temp, 1),
            oil_pressure=round(oil_pressure, 2),
            rpm_alert_min=rpm_alert_min,
            rpm_alert_max=rpm_alert_max,
            tcs_active=bool(flags & FLAG_TCS_ACTIVE),
            asm_active=bool(flags & FLAG_ASM_ACTIVE),
            handbrake=bool(flags & FLAG_HANDBRAKE),
            rev_limiter=bool(flags & FLAG_REV_LIMITER),
            car_on_track=bool(flags & FLAG_CAR_ON_TRACK),
            paused=paused,
            car_id=car_id,
            packet_format=SIZE_TO_FORMAT.get(len(data), "A"),
            source_game="gt7",
        )
    except struct.error as e:
        logger.debug(f"Parse error: {e}")
        return None


class GT7TelemetryService:
    def __init__(self):
        self.status = ConnectionStatus(game="gt7")
        self._on_frame_callbacks: list[Callable[[TelemetryFrame], Awaitable[None]]] = []
        self._ps5_addr: Optional[tuple] = None
        self._sock: Optional[socket.socket] = None
        self._running = False
        self._heartbeat_payload = settings.GT7_PACKET_FORMAT.encode("ascii")

    def on_frame(self, cb: Callable[[TelemetryFrame], Awaitable[None]]):
        self._on_frame_callbacks.append(cb)

    def set_ps5_address(self, ip: str, port: int = None):
        self._ps5_addr = (ip, port or settings.GT7_PS_PORT)
        logger.info(f"PS5 address set to {self._ps5_addr[0]}:{self._ps5_addr[1]}")

    async def start(self):
        self._running = True
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._sock.bind((settings.GT7_BIND_IP, settings.GT7_UDP_PORT))
        self._sock.setblocking(False)
        logger.info(f"GT7 UDP listener started on :{settings.GT7_UDP_PORT} "
                    f"(requesting packet format {settings.GT7_PACKET_FORMAT!r})")
        loop = asyncio.get_event_loop()
        asyncio.create_task(self._heartbeat_loop())
        while self._running:
            try:
                data, addr = await loop.run_in_executor(None, self._recv)
                if data:
                    await self._handle_packet(data, addr)
            except Exception as e:
                logger.debug(f"Recv error: {e}")
                await asyncio.sleep(0.01)

    def stop(self):
        self._running = False
        if self._sock:
            self._sock.close()

    def _recv(self):
        try:
            return self._sock.recvfrom(4096)
        except BlockingIOError:
            return None, None

    async def _heartbeat_loop(self):
        while self._running:
            try:
                if self._ps5_addr:
                    self._sock.sendto(self._heartbeat_payload, self._ps5_addr)
                else:
                    self._sock.sendto(self._heartbeat_payload, ("255.255.255.255", settings.GT7_PS_PORT))
            except Exception:
                pass
            await asyncio.sleep(0.1)

    async def _handle_packet(self, data: bytes, addr: tuple):
        if not self._ps5_addr:
            self._ps5_addr = (addr[0], settings.GT7_PS_PORT)
            logger.info(f"PS5 auto-discovered at {addr[0]}")

        decrypted = _decrypt_packet(data)
        if not decrypted:
            return
        frame = _parse_frame(decrypted)
        if not frame:
            return

        self.status.connected = True
        self.status.source_ip = addr[0]
        self.status.frames_received += 1
        self.status.packet_format = frame.packet_format
        self.status.last_seen = time.time()

        for cb in self._on_frame_callbacks:
            await cb(frame)