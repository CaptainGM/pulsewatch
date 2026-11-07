import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import settings
from app.models import utcnow
from app.security import require_ws_access
from app.services.events import events

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    if not await require_ws_access(websocket.query_params.get("token")):
        await websocket.close(code=4401)
        return
    await events.connect(websocket)
    try:
        await websocket.send_json(
            {
                "type": "hello",
                "version": settings.version,
                "server_time": utcnow().isoformat(),
            }
        )
        while True:
            message = await websocket.receive_text()
            if message == "ping":
                await websocket.send_json({"type": "pong", "server_time": utcnow().isoformat()})
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.debug("WebSocket closed: %s", exc)
    finally:
        events.disconnect(websocket)
