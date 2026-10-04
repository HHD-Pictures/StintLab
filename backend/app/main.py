"""
StintLab Backend — main entry point.
"""

import asyncio
import logging

from app.services.telemetry_service import GT7TelemetryService
from app.services.strategy_service import StrategyService
from app.services.event_detector import EventDetector
from app.websocket.telemetry import TelemetryWebSocketServer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger("stintlab")


async def main():
    logger.info("StintLab backend starting…")

    telemetry = GT7TelemetryService()
    strategy = StrategyService()
    events = EventDetector()
    ws_server = TelemetryWebSocketServer(telemetry, strategy, events)

    await ws_server.start()

    logger.info("All services online. Waiting for telemetry")

    await asyncio.gather(
        telemetry.start(),
        asyncio.sleep(float("inf")),
    )