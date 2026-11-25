"""设备控制后端 —— 把原仓库「脚本直连设备」抽成可复用的 DeviceService。

设计要点
--------
1. 设备清单：devices.json（不存在则回退 devices.example.json），带 id/名称/类型/IP/token。
2. 真机后端：空气净化器/插座走 python-miio，灯走 yeelight；调用失败或未配置 IP/token
   时自动降级为内存模拟（返回 backend="simulated"），保证无硬件也能演示。
3. 所有写操作先校验「设备是否支持该能力」+「参数范围」，再执行。
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
DEVICES_FILE = BASE_DIR / "devices.json"
EXAMPLE_FILE = BASE_DIR / "devices.example.json"

# 设备类型 → 支持的能力
CAPABILITIES: dict[str, tuple[str, ...]] = {
    "light": ("power", "brightness", "color_temp"),
    "airpurifier": ("power", "mode", "favorite_level", "aqi"),
    "plug": ("power",),
}

# 参数范围（越界直接拒绝，不发给设备）
RANGES: dict[str, tuple[int, int]] = {
    "brightness": (1, 100),
    "color_temp": (1700, 6500),
    "favorite_level": (1, 14),
}

PURIFIER_MODES = ("auto", "silent", "favorite", "idle")


class DeviceError(Exception):
    """设备不存在 / 不支持该能力 / 参数越界。"""


@dataclass(frozen=True)
class Device:
    id: str
    name: str
    type: str
    ip: str = ""
    token: str = ""
    room: str = ""
    capabilities: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Device":
        device_type = raw["type"]
        return cls(
            id=raw["id"],
            name=raw.get("name", raw["id"]),
            type=device_type,
            ip=raw.get("ip", ""),
            token=raw.get("token", ""),
            room=raw.get("room", ""),
            capabilities=tuple(raw.get("capabilities") or CAPABILITIES.get(device_type, ())),
        )

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "room": self.room,
            "capabilities": list(self.capabilities),
        }


class DeviceRegistry:
    def __init__(self, path: str | Path | None = None) -> None:
        source = Path(path) if path else (DEVICES_FILE if DEVICES_FILE.exists() else EXAMPLE_FILE)
        raw = json.loads(source.read_text(encoding="utf-8"))
        items = raw.get("devices", raw) if isinstance(raw, dict) else raw
        self._devices: dict[str, Device] = {}
        for item in items:
            device = Device.from_dict(item)
            self._devices[device.id] = device
        logger.info("加载设备 %d 台，来源 %s", len(self._devices), source.name)

    def all(self) -> list[Device]:
        return list(self._devices.values())

    def get(self, device_id: str) -> Device:
        device = self._devices.get(device_id)
        if device is None:
            raise DeviceError(f"未知设备 {device_id}；可选: {', '.join(self._devices)}")
        return device

    def find(self, text: str) -> Device | None:
        """按 id / 名称 / 房间模糊匹配，供自然语言解析使用。"""
        for device in self._devices.values():
            if device.id in text or device.name in text:
                return device
        for device in self._devices.values():
            if device.room and device.room in text:
                return device
        return None


class DeviceService:
    def __init__(self, registry: DeviceRegistry | None = None) -> None:
        self.registry = registry or DeviceRegistry()
        self._state: dict[str, dict[str, Any]] = {
            d.id: {
                "power": False,
                "brightness": 60,
                "color_temp": 4000,
                "mode": "auto",
                "favorite_level": 5,
                "aqi": 42,
            }
            for d in self.registry.all()
        }
        self._lock = threading.Lock()

    # ── 读 ────────────────────────────────────────────────────────────────

    def list_devices(self) -> list[dict[str, Any]]:
        return [d.public() for d in self.registry.all()]

    def status(self, device_id: str) -> dict[str, Any]:
        device = self.registry.get(device_id)
        state = dict(self._state[device_id])
        if device.type == "airpurifier":
            state = {k: state[k] for k in ("power", "mode", "favorite_level", "aqi")}
        elif device.type == "light":
            state = {k: state[k] for k in ("power", "brightness", "color_temp")}
        else:
            state = {"power": state["power"]}
        return {"device": device.public(), "state": state}

    # ── 写 ────────────────────────────────────────────────────────────────

    def set_power(self, device_id: str, on: bool) -> dict[str, Any]:
        self._require(device_id, "power")
        return self._write(device_id, "power", bool(on))

    def set_brightness(self, device_id: str, brightness: int) -> dict[str, Any]:
        self._require(device_id, "brightness")
        self._in_range("brightness", brightness)
        return self._write(device_id, "brightness", int(brightness))

    def set_color_temp(self, device_id: str, kelvin: int) -> dict[str, Any]:
        self._require(device_id, "color_temp")
        self._in_range("color_temp", kelvin)
        return self._write(device_id, "color_temp", int(kelvin))

    def set_mode(self, device_id: str, mode: str) -> dict[str, Any]:
        self._require(device_id, "mode")
        if mode not in PURIFIER_MODES:
            raise DeviceError(f"不支持的模式 {mode}；可选: {', '.join(PURIFIER_MODES)}")
        return self._write(device_id, "mode", mode)

    def set_favorite_level(self, device_id: str, level: int) -> dict[str, Any]:
        self._require(device_id, "favorite_level")
        self._in_range("favorite_level", level)
        return self._write(device_id, "favorite_level", int(level))

    # ── 内部 ──────────────────────────────────────────────────────────────

    def _require(self, device_id: str, capability: str) -> Device:
        device = self.registry.get(device_id)
        if capability not in device.capabilities:
            raise DeviceError(f"{device.name} 不支持 {capability}")
        return device

    @staticmethod
    def _in_range(name: str, value: int) -> None:
        low, high = RANGES[name]
        if not low <= int(value) <= high:
            raise DeviceError(f"{name} 需在 {low}–{high} 之间，收到 {value}")

    def _write(self, device_id: str, key: str, value: Any) -> dict[str, Any]:
        device = self.registry.get(device_id)
        with self._lock:
            backend = self._apply(device, key, value)
            self._state[device_id][key] = value
            return {
                "ok": True,
                "backend": backend,
                "device": device.public(),
                "change": {key: value},
                **self.status(device_id),
            }

    def _apply(self, device: Device, key: str, value: Any) -> str:
        """真机执行；不可用时返回 simulated，由调用方降级。"""
        if not device.ip:
            return "simulated"
        try:
            if device.type == "airpurifier":
                from miio.airpurifier import AirPurifier  # 仓库内置旧版 miio（Python 3.6）

                purifier = AirPurifier(device.ip, device.token)
                if key == "power":
                    purifier.on() if value else purifier.off()
                elif key == "mode":
                    purifier.set_mode(value)
                elif key == "favorite_level":
                    purifier.set_favorite_level(value)
                return "miio"
            if device.type == "light":
                from yeelight import Bulb

                bulb = Bulb(device.ip)
                if key == "power":
                    bulb.turn_on() if value else bulb.turn_off()
                elif key == "brightness":
                    bulb.set_brightness(value)
                elif key == "color_temp":
                    bulb.set_color_temp(value)
                return "yeelight"
        except Exception as exc:  # noqa: BLE001 - 真机异常一律降级，不阻断演示
            logger.warning("设备 %s 真机调用失败，降级模拟: %s", device.id, exc)
        return "simulated"


_service: DeviceService | None = None


def get_service() -> DeviceService:
    global _service
    if _service is None:
        _service = DeviceService()
    return _service
