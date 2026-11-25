"""设备控制 Agent 的 LangGraph 图：解析 → 安全校验 → 执行 → 生成回复。

和「客服 Agent」的分工：
- 客服 Agent 负责对话与售后流程，需要动硬件时通过 MCP 调用 mcp_server.py；
- 本图是设备侧的最小可运行 Agent，直接复用 device_tools，用于本地演示 / 单测。

图：
    START → parse → guard ─┬─(blocked)→ reply → END
                           └─(ok)──────→ act ──→ reply → END
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from device_driver import Device, DeviceError, get_service

from .device_tools import (
    get_device_status,
    set_brightness,
    set_color_temp,
    set_power,
    set_purifier_mode,
)

# ── 状态 ─────────────────────────────────────────────────────────────────────

Action = Literal[
    "power_on",
    "power_off",
    "brightness",
    "color_temp",
    "mode",
    "status",
    "list",
    "unknown",
]


class DeviceState(TypedDict, total=False):
    text: str
    device_id: str
    device_name: str
    action: str
    params: dict[str, Any]
    blocked: bool
    block_reason: str
    result: dict[str, Any]
    reply: str


# ── 解析规则 ─────────────────────────────────────────────────────────────────

POWER_ON = ("打开", "开灯", "开启", "开机", "通电", "启动")
POWER_OFF = ("关闭", "关灯", "关掉", "关机", "断电", "停止")
MODE_WORDS = {"自动": "auto", "静音": "silent", "睡眠": "idle", "最爱": "favorite", "收藏": "favorite"}
WARM_WORDS = ("暖光", "暖色", "黄光", "柔和")
COOL_WORDS = ("冷光", "冷色", "白光", "明亮")

# 危险操作：设备侧 Agent 一律不做（改网关、恢复出厂、重启等）
DANGEROUS = ("恢复出厂", "重置设备", "重启网关", "删除设备", "token", "刷机", "固件")


def _pick_device(text: str) -> Device | None:
    return get_service().registry.find(text)


def parse_node(state: DeviceState) -> dict[str, Any]:
    text = state["text"].strip()
    device = _pick_device(text)

    if any(word in text for word in DANGEROUS):
        return {"action": "unknown", "blocked": False}

    if not device:
        if "有哪些" in text or "列表" in text or "设备" in text and "什么" in text:
            return {"action": "list"}
        return {"action": "unknown", "block_reason": "没有识别到具体设备，请说明是哪个房间的哪台设备。"}

    update: dict[str, Any] = {"device_id": device.id, "device_name": device.name}
    capability = device.capabilities

    if "状态" in text or "怎么样" in text or "多少" in text or "查询" in text:
        return {**update, "action": "status"}

    percent = re.search(r"(\d{1,3})\s*%", text)
    kelvin = re.search(r"(\d{4})\s*(?:k|K)", text)

    if "brightness" in capability:
        if percent:
            return {**update, "action": "brightness", "params": {"value": int(percent.group(1))}}
        if any(w in text for w in ("亮度", "亮一点", "暗一点", "调亮", "调暗")):
            current = int(get_service().status(device.id)["state"].get("brightness", 60))
            delta = 20 if any(w in text for w in ("亮一点", "调亮", "太暗")) else -20
            return {
                **update,
                "action": "brightness",
                "params": {"value": max(1, min(100, current + delta))},
            }

    if "color_temp" in capability:
        if kelvin:
            return {**update, "action": "color_temp", "params": {"value": int(kelvin.group(1))}}
        if any(w in text for w in WARM_WORDS):
            return {**update, "action": "color_temp", "params": {"value": 2700}}
        if any(w in text for w in COOL_WORDS):
            return {**update, "action": "color_temp", "params": {"value": 6500}}

    if "mode" in capability:
        for word, mode in MODE_WORDS.items():
            if word in text:
                return {**update, "action": "mode", "params": {"value": mode}}

    if "power" in capability:
        if any(w in text for w in POWER_OFF):
            return {**update, "action": "power_off", "params": {"on": False}}
        if any(w in text for w in POWER_ON):
            return {**update, "action": "power_on", "params": {"on": True}}

    return {**update, "action": "unknown", "block_reason": f"{device.name} 没听懂要执行什么操作。"}


def guard_node(state: DeviceState) -> dict[str, Any]:
    """执行前的安全闸门：危险指令、未知设备、未解析动作都在这里拦下。"""
    text = state["text"]
    if any(word in text for word in DANGEROUS):
        return {"blocked": True, "block_reason": "改网关 / 恢复出厂 / 固件操作超出权限，请走人工运维。"}

    action = state.get("action", "unknown")
    if action in ("list", "status"):
        return {"blocked": False}

    if state.get("blocked"):
        return {}

    device_id = state.get("device_id")
    if not device_id:
        return {"blocked": True, "block_reason": state.get("block_reason", "未识别到设备。")}

    try:
        device = get_service().registry.get(device_id)
    except DeviceError as exc:
        return {"blocked": True, "block_reason": str(exc)}

    capability = {
        "power_on": "power",
        "power_off": "power",
        "brightness": "brightness",
        "color_temp": "color_temp",
        "mode": "mode",
    }.get(action)
    if capability and capability not in device.capabilities:
        return {"blocked": True, "block_reason": f"{device.name} 不支持 {capability} 操作。"}

    return {"blocked": False}


def route_after_guard(state: DeviceState) -> str:
    return "reply" if state.get("blocked") else "act"


def act_node(state: DeviceState) -> dict[str, Any]:
    action = state.get("action", "unknown")
    params = state.get("params") or {}
    device_id = state.get("device_id", "")

    tool_call = {
        "list": lambda: get_service().list_devices(),
        "status": lambda: get_device_status.invoke({"device_id": device_id}),
        "power_on": lambda: set_power.invoke({"device_id": device_id, "on": True}),
        "power_off": lambda: set_power.invoke({"device_id": device_id, "on": False}),
        "brightness": lambda: set_brightness.invoke(
            {"device_id": device_id, "brightness": int(params.get("value", 60))}
        ),
        "color_temp": lambda: set_color_temp.invoke(
            {"device_id": device_id, "kelvin": int(params.get("value", 4000))}
        ),
        "mode": lambda: set_purifier_mode.invoke(
            {"device_id": device_id, "mode": str(params.get("value", "auto"))}
        ),
    }.get(action)

    if tool_call is None:
        return {"result": {"ok": False, "error": "unsupported action"}}

    try:
        raw = tool_call()
    except Exception as exc:  # noqa: BLE001 - 工具内部已返回错误 JSON，这里兜底
        return {"result": {"ok": False, "error": str(exc)}}

    return {"result": json.loads(raw) if isinstance(raw, str) else raw}


def reply_node(state: DeviceState) -> dict[str, Any]:
    if state.get("blocked"):
        return {"reply": f"⚠️ {state.get('block_reason', '操作被拦截')}"}

    result = state.get("result") or {}
    action = state.get("action", "unknown")

    if action == "list":
        devices = result.get("devices", [])
        lines = [f"- {d['name']}（{d['id']}，{d['type']}）" for d in devices]
        return {"reply": "当前可用设备：\n" + "\n".join(lines)}

    if not result.get("ok", False):
        return {"reply": f"❌ 执行失败：{result.get('error', '未知错误')}"}

    name = result.get("device", {}).get("name", state.get("device_name", "设备"))
    state_now = result.get("state", {})
    backend = result.get("backend", "")

    if action == "status":
        detail = "，".join(f"{k}={v}" for k, v in state_now.items())
        return {"reply": f"{name} 当前状态：{detail}（backend={backend}）"}

    changed = result.get("change", {})
    detail = "，".join(f"{k}={v}" for k, v in changed.items())
    return {"reply": f"✅ 已对 {name} 执行 {detail}（backend={backend}）"}


# ── 装配 ─────────────────────────────────────────────────────────────────────

def build_graph(checkpointer: MemorySaver | None = None):
    graph = StateGraph(DeviceState)
    graph.add_node("parse", parse_node)
    graph.add_node("guard", guard_node)
    graph.add_node("act", act_node)
    graph.add_node("reply", reply_node)

    graph.add_edge(START, "parse")
    graph.add_edge("parse", "guard")
    graph.add_conditional_edges("guard", route_after_guard, {"reply": "reply", "act": "act"})
    graph.add_edge("act", "reply")
    graph.add_edge("reply", END)

    return graph.compile(checkpointer=checkpointer or MemorySaver())


_compiled = None


def get_graph():
    global _compiled
    if _compiled is None:
        _compiled = build_graph()
    return _compiled
