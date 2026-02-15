"""Task status and WebSocket endpoints."""
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, HTTPException
from api.deps import get_task_manager

router = APIRouter(tags=["tasks"])


@router.get("/tasks/{task_id}")
async def get_task_status(task_id: str, tm=Depends(get_task_manager)):
    record = tm.get_task(task_id)
    if not record:
        raise HTTPException(404, "Task not found")
    result = {
        "id": record.id,
        "kind": record.kind,
        "status": record.status.value,
        "progress": record.progress,
        "message": record.message,
    }
    if record.result is not None:
        result["result"] = record.result
    if record.error is not None:
        result["error"] = record.error
    return result


@router.websocket("/ws/tasks/{task_id}")
async def task_websocket(websocket: WebSocket, task_id: str, tm=Depends(get_task_manager)):
    await websocket.accept()
    record = tm.get_task(task_id)
    if not record:
        await websocket.send_json({"type": "error", "message": "Task not found"})
        await websocket.close()
        return

    # Send current state immediately
    await websocket.send_json({
        "type": "progress",
        "taskId": record.id,
        "status": record.status.value,
        "progress": record.progress,
        "message": record.message,
    })

    await tm.subscribe(task_id, websocket)
    try:
        while True:
            # Keep connection alive, wait for client messages
            await websocket.receive_text()
    except WebSocketDisconnect:
        await tm.unsubscribe(task_id, websocket)
