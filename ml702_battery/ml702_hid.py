"""Actively query Thunderobot ML702 battery over HID.

Jiangmeng/Pulsar-family frame: report 0x08, command 0x04,
usage page 0xFF02 / usage 0x0002.
"""

from __future__ import annotations

import ctypes
import threading
import time
from dataclasses import dataclass

import hid

VID = 0x3554
PID_WIRELESS = 0xF501
PID_WIRED = 0xF500
USAGE_PAGE = 0xFF02
USAGE = 0x0002

# Li-ion pack range for sanity checks (mV)
_MV_MIN = 2500
_MV_MAX = 4500

_lock = threading.Lock()


@dataclass(frozen=True)
class BatteryInfo:
    percent: int
    millivolts: int
    charging: bool
    raw: bytes


def _checksum(*values: int) -> int:
    return ctypes.c_uint8(0x55 - sum(values)).value


def _power_request() -> bytes:
    payload = [0x08, 0x04] + [0] * 14
    payload = payload[:16]
    return bytes(payload + [_checksum(*payload)])


def _find_path(pids: tuple[int, ...] = (PID_WIRELESS, PID_WIRED)) -> bytes | None:
    preferred: bytes | None = None
    fallback: bytes | None = None
    for pid in pids:
        for d in hid.enumerate(VID, pid):
            if d["usage_page"] == USAGE_PAGE and d["usage"] == USAGE:
                preferred = d["path"]
                break
            if d["usage_page"] >= 0xFF00 and fallback is None:
                fallback = d["path"]
        if preferred:
            return preferred
    return preferred or fallback


def _normalize(raw: bytes) -> bytes | None:
    if not raw:
        return None
    data = bytes(raw)
    if data[0] != 0x08:
        data = bytes([0x08]) + data
    if len(data) < 17:
        return None
    return data[:17]


def _parse_power_reply(data: bytes, request: bytes) -> BatteryInfo | None:
    """Accept only a real power *reply*, not the request echo or junk."""
    if data[1] != 0x04:
        return None
    if data[16] != _checksum(*data[:16]):
        return None
    # Drop write-echo / empty shell of the request itself
    if data == request:
        return None
    # Official-style reply sets a non-zero length/status at byte5, and/or mV
    mv = int.from_bytes(data[8:10], "big")
    pct = int(data[6])
    if pct > 100:
        return None
    has_payload_flag = data[5] != 0
    has_voltage = _MV_MIN <= mv <= _MV_MAX
    if not (has_payload_flag or has_voltage):
        return None
    if has_voltage is False and pct == 0 and data[7] == 0:
        # Likely empty/echo-like frame
        return None
    return BatteryInfo(
        percent=pct,
        millivolts=mv if has_voltage else 0,
        charging=bool(data[7]),
        raw=data,
    )


def _flush(h: hid.device, rounds: int = 40) -> None:
    """Drain leftover input reports so we don't parse stale frames."""
    for _ in range(rounds):
        chunk = h.read(64)
        if not chunk:
            break


def _query_once(h: hid.device, timeout_s: float) -> BatteryInfo:
    req = _power_request()
    _flush(h)
    written = h.write(req)
    if written < 0:
        raise OSError("HID write failed")

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        raw = h.read(64)
        if not raw:
            time.sleep(0.01)
            continue
        data = _normalize(raw)
        if data is None:
            continue
        info = _parse_power_reply(data, req)
        if info is not None:
            return info
    raise TimeoutError("主动查询无有效应答")


def read_battery(
    timeout_s: float = 0.8,
    attempts: int = 3,
    retry_gap_s: float = 0.12,
) -> BatteryInfo:
    """Actively send power-query frames until a valid reply arrives."""
    path = _find_path()
    if path is None:
        raise RuntimeError("未找到 ML702 接收器 (3554:F501/F500)")

    with _lock:
        h = hid.device()
        h.open_path(path)
        try:
            h.set_nonblocking(1)
            last_err: Exception | None = None
            for i in range(attempts):
                try:
                    return _query_once(h, timeout_s=timeout_s)
                except Exception as e:
                    last_err = e
                    if i + 1 < attempts:
                        time.sleep(retry_gap_s)
            assert last_err is not None
            raise last_err
        finally:
            h.close()


if __name__ == "__main__":
    for n in range(5):
        info = read_battery()
        state = "充电中" if info.charging else "放电"
        print(f"#{n+1} {info.percent}%  {info.millivolts} mV  {state}  raw={info.raw.hex()}")
        time.sleep(0.5)
