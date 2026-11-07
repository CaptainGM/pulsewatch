import asyncio
import json
import logging
import uuid
from typing import Any

from fastapi import WebSocket

from app.services.cache import cache

logger = logging.getLogger(__name__)

EVENTS_CHANNEL = "pulsewatch:events"
INSTANCE_ID = uuid.uuid4().hex


class EventHub:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._subscriber_task: asyncio.Task | None = None
        self._pubsub = None

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.discard(websocket)

    async def broadcast(self, event: dict[str, Any]) -> None:
        if not self._connections:
            return
        payload = json.dumps(event, default=str, ensure_ascii=False)
        dead: list[WebSocket] = []
        for websocket in list(self._connections):
            try:
                await websocket.send_text(payload)
            except Exception:
                dead.append(websocket)
        for websocket in dead:
            self.disconnect(websocket)

    async def publish(self, event: dict[str, Any]) -> None:
        event = {**event, "_origin": INSTANCE_ID}
        await self.broadcast(event)
        await cache.publish(EVENTS_CHANNEL, event)

    async def start(self) -> None:
        if cache.redis is None:
            return
        self._pubsub = await cache.subscribe(EVENTS_CHANNEL)
        if self._pubsub is not None:
            self._subscriber_task = asyncio.create_task(self._listen(), name="event-hub-subscriber")
            logger.info("Redis event subscriber started")

    async def stop(self) -> None:
        if self._subscriber_task is not None:
            self._subscriber_task.cancel()
            try:
                await self._subscriber_task
            except (asyncio.CancelledError, Exception):
                pass
            self._subscriber_task = None
        if self._pubsub is not None:
            try:
                await self._pubsub.unsubscribe(EVENTS_CHANNEL)
                await self._pubsub.aclose()
            except Exception:
                pass
            self._pubsub = None

    async def _listen(self) -> None:
        assert self._pubsub is not None
        try:
            async for message in self._pubsub.listen():
                if message.get("type") != "message":
                    continue
                try:
                    event = json.loads(message["data"])
                except (TypeError, ValueError):
                    continue
                if event.get("_origin") == INSTANCE_ID:
                    continue
                await self.broadcast(event)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Redis event subscriber stopped: %s", exc)


events = EventHub()
