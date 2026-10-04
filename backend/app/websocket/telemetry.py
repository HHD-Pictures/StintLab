"""
WebSocket server — broadcasts TelemetryFrame, StrategyProjection and
LiveEvent JSON to all connected frontend clients.
"""

import asyncio
import json
import logging
import time
from typing import Optional, Set

import websockets
from websockets.asyncio.server import ServerConnection

from app.models.telemetry import TelemetryFrame
from app.core.config import settings
from app.services.strategy_service import StrategyService
from app.services.event_detector import EventDetector

logger = logging.getLogger(__name__)


class TelemetryWebSocketServer:
    def __init__(
        self,
        telemetry_service,
        strategy_service: Optional[StrategyService] = None,
        event_detector: Optional[EventDetector] = None,
    ):
        self.telemetry_service = telemetry_service
        self.strategy_service = strategy_service or StrategyService()
        self.event_detector = event_detector or EventDetector()
        self._clients: Set[ServerConnection] = set()
        self._server = None

    async def start(self):
        self.telemetry_service.on_frame(self._broadcast_frame)
        self._server = await websockets.serve(
            self._handle_client,
            settings.WS_HOST,
            settings.WS_PORT,
        )
        logger.info(f"WebSocket server started on ws://{settings.WS_HOST}:{settings.WS_PORT}")

    async def _handle_client(self, ws: ServerConnection):
        self._clients.add(ws)
        logger.info(f"Client connected (total: {len(self._clients)})")
        await self._send_status(ws)
        try:
            async for message in ws:
                await self._handle_message(ws, message)
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self._clients.discard(ws)
            logger.info(f"Client disconnected (total: {len(self._clients)})")

    async def _handle_message(self, ws: ServerConnection, message: str):
        try:
            msg = json.loads(message)
            action = msg.get("action")
            if action == "set_ps5_ip":
                ip = msg.get("ip", "")
                if ip:
                    self.telemetry_service.set_ps5_address(ip)
                    await self._send_json(ws, {"type": "ack", "action": "set_ps5_ip", "ip": ip, "ok": True})
            elif action == "get_status":
                await self._send_status(ws)
            elif action == "ping":
                await self._send_json(ws, {"type": "pong", "ts": time.time()})
        except json.JSONDecodeError:
            pass

    async def _broadcast_frame(self, frame: TelemetryFrame):
        if not self._clients:
            return

        payload = json.dumps({"type": "telemetry", "data": frame.model_dump()})
        dead = set()
        for ws in self._clients:
            try:
                await ws.send(payload)
            except Exception:
                dead.add(ws)
        self._clients -= dead

        # Strategy projection and live events piggyback on the same frame
        # cadence — cheap to compute, and the Pitwall wants them in lockstep
        # with telemetry rather than on their own timer.
        strategy = self.strategy_service.on_frame(frame)
        if strategy:
            strategy_payload = json.dumps({"type": "strategy", "data": strategy.model_dump()})
            for ws in list(self._clients):
                try:
                    await ws.send(strategy_payload)
                except Exception:
                    self._clients.discard(ws)

        for event in self.event_detector.check(frame, strategy):
            event_payload = json.dumps({"type": "event", "data": event.model_dump()})
            for ws in list(self._clients):
                try:
                    await ws.send(event_payload)
                except Exception:
                    self._clients.discard(ws)

    async def _send_status(self, ws: ServerConnection):
        status = self.telemetry_service.status
        await self._send_json(ws, {"type": "status", "data": status.model_dump()})

    @staticmethod
    async def _send_json(ws: ServerConnection, data: dict):
        try:
            await ws.send(json.dumps(data))
        except Exception:
            pass