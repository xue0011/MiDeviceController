"""设备控制 Agent 的 FastAPI 入口。

本地运行（cwd 必须是 ControlXiaomiDevices，才能 import device_driver）：
    python -m agent
    # 或 uvicorn agent.api:app --port 8020
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from device_driver import DeviceError, get_service

from .graph import get_graph

app = FastAPI(title="Xiaomi Device Agent", version="0.1.0")


class ChatIn(BaseModel):
    text: str = Field(..., examples=["把客厅灯调暗一点"])
    thread_id: str = Field("demo", examples=["home-001"])


class ChatOut(BaseModel):
    reply: str
    action: str
    device_id: str | None = None
    result: dict[str, Any] | None = None
    blocked: bool = False


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "devices": len(get_service().list_devices())}


@app.get("/devices")
def devices() -> dict[str, Any]:
    return {"devices": get_service().list_devices()}


@app.get("/devices/{device_id}")
def device_status(device_id: str) -> dict[str, Any]:
    try:
        return get_service().status(device_id)
    except DeviceError as exc:
        return {"ok": False, "error": str(exc)}


class PowerIn(BaseModel):
    on: bool


@app.post("/devices/{device_id}/power")
def set_power(device_id: str, body: PowerIn) -> dict[str, Any]:
    try:
        return get_service().set_power(device_id, body.on)
    except DeviceError as exc:
        return {"ok": False, "error": str(exc)}


@app.post("/chat", response_model=ChatOut)
def chat(body: ChatIn) -> ChatOut:
    graph = get_graph()
    state = graph.invoke(
        {"text": body.text},
        config={"configurable": {"thread_id": body.thread_id}},
    )
    return ChatOut(
        reply=state.get("reply", ""),
        action=state.get("action", "unknown"),
        device_id=state.get("device_id"),
        result=state.get("result"),
        blocked=bool(state.get("blocked")),
    )


@app.get("/graph")
def graph_mermaid() -> dict[str, str]:
    return {"mermaid": get_graph().get_graph().draw_mermaid()}
