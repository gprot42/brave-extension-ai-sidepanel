"""WebSocket endpoint for real-time heart rate streaming."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.data.sync import hr_subscribers

ws_router = APIRouter()


@ws_router.websocket("/ws/hr")
async def hr_websocket(websocket: WebSocket):
    await websocket.accept()

    async def send_fn(data: str):
        await websocket.send_text(data)

    hr_subscribers.append(send_fn)
    try:
        while True:
            # Keep connection alive; client can send pings
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        if send_fn in hr_subscribers:
            hr_subscribers.remove(send_fn)
