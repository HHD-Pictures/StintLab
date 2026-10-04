from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # WebSocket server
    WS_HOST: str = "0.0.0.0"
    WS_PORT: int = 8765

    # GT7 UDP listener
    GT7_UDP_PORT: int = 33740
    GT7_BIND_IP: str = "0.0.0.0"
    GT7_PS_PORT: int = 33739

    # Packet format requested from the console via the heartbeat: A, B, ~, or C.
    # A (296B) is the safe default — everything StintLab currently decodes lives
    # inside it. B/~/C add steering, accel and per-wheel surface, but this
    # codebase doesn't have verified offsets for those yet (see
    # telemetry_service.py TODOs), so switching this only grows the datagram —
    # it doesn't unlock new fields on its own.
    GT7_PACKET_FORMAT: str = "A"

    # Salsa20 decryption key (GT7 uses this for telemetry packets)
    GT7_SALSA_KEY: bytes = b"Simulator Interface Packet GT7 ver 0.0"

    # Rolling window (laps) for the fuel/pit strategy projection.
    # short enough to react to a
    # fuel-map change, long enough to smooth out one noisy lap.
    STRATEGY_WINDOW_LAPS: int = 3

    class Config:
        env_file = ".env"


settings = Settings()