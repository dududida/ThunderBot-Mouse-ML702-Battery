"""System tray battery indicator for Thunderobot ML702."""

from __future__ import annotations

import ctypes
import sys
import threading
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
import pystray

from ml702_hid import BatteryInfo, read_battery

POLL_SECONDS = 3  # active query interval
LOW_PERCENT = 20


def _enable_dpi_awareness() -> None:
    """Prefer per-monitor DPI so tray bitmap matches physical pixels."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def _tray_icon_px() -> int:
    """Physical pixel size Windows expects for a small icon."""
    try:
        # SM_CXSMICON = 49
        cx = int(ctypes.windll.user32.GetSystemMetrics(49))
        if cx >= 16:
            # Render 2× then let shell scale once → sharper on many setups,
            # but for text icons exact size is usually crispest.
            return max(cx, 32)
    except Exception:
        pass
    try:
        dpi = int(ctypes.windll.user32.GetDpiForSystem())
        return max(32, int(round(16 * dpi / 96.0 * 2)))
    except Exception:
        return 64


def _resource_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def _level_color(percent: int | None, charging: bool) -> tuple[int, int, int]:
    if percent is None:
        return (127, 140, 141)
    if charging:
        return (39, 174, 96)
    if percent <= LOW_PERCENT:
        return (192, 57, 43)
    if percent <= 40:
        return (211, 84, 0)
    return (41, 128, 185)


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path(r"C:\Windows\Fonts\segoeuib.ttf"),
        Path(r"C:\Windows\Fonts\seguisb.ttf"),
        Path(r"C:\Windows\Fonts\arialbd.ttf"),
        Path(r"C:\Windows\Fonts\msyhbd.ttc"),
        _resource_dir() / "segoeuib.ttf",
    ]
    for path in candidates:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _draw_lightning(draw: ImageDraw.ImageDraw, cx: int, cy: int, scale: float) -> None:
    s = scale
    pts = [
        (cx - 2 * s, cy - 10 * s),
        (cx + 5 * s, cy - 10 * s),
        (cx + 1 * s, cy - 1 * s),
        (cx + 7 * s, cy - 1 * s),
        (cx - 4 * s, cy + 11 * s),
        (cx - 1 * s, cy + 1 * s),
        (cx - 7 * s, cy + 1 * s),
    ]
    draw.polygon(pts, fill=(255, 255, 255))


def make_icon(
    percent: int | None,
    charging: bool = False,
    size: int | None = None,
) -> Image.Image:
    size = int(size or _tray_icon_px())
    # Internal supersample for ClearType-like edges, then box-downsample.
    scale = 4 if size < 96 else 2
    canvas = size * scale
    img = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    color = _level_color(percent, charging)

    margin = max(2 * scale, canvas // 16)
    radius = canvas // 5
    draw.rounded_rectangle(
        (margin, margin, canvas - margin, canvas - margin),
        radius=radius,
        fill=color,
    )

    if percent is None:
        text = "?"
    elif percent >= 100:
        text = "100"
    else:
        text = str(int(percent))

    if len(text) >= 3:
        font_size = canvas * 40 // 100
    elif len(text) == 2:
        font_size = canvas * 50 // 100
    else:
        font_size = canvas * 58 // 100

    font = _load_font(font_size)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

    if charging:
        bolt_space = canvas // 5
        total_w = tw + bolt_space // 2
        tx = (canvas - total_w) // 2 - bbox[0]
        ty = (canvas - th) // 2 - bbox[1] - canvas // 80
        # 1px-equivalent outline via multi-pass (stays sharp after downsample)
        outline = max(scale, canvas // 64)
        for ox, oy in (
            (-outline, 0),
            (outline, 0),
            (0, -outline),
            (0, outline),
            (-outline, -outline),
            (outline, outline),
            (-outline, outline),
            (outline, -outline),
        ):
            draw.text((tx + ox, ty + oy), text, font=font, fill=(0, 0, 0, 160))
        draw.text((tx, ty), text, font=font, fill=(255, 255, 255))
        bx = tx + tw + bolt_space // 3
        by = canvas // 2
        _draw_lightning(draw, bx, by, max(2.0, canvas / 48.0))
        bar_h = max(2 * scale, canvas // 18)
        draw.rounded_rectangle(
            (
                margin + canvas // 8,
                margin,
                canvas - margin - canvas // 8,
                margin + bar_h,
            ),
            radius=bar_h // 2,
            fill=(255, 255, 255, 230),
        )
    else:
        tx = (canvas - tw) // 2 - bbox[0]
        ty = (canvas - th) // 2 - bbox[1] - canvas // 80
        outline = max(scale, canvas // 64)
        for ox, oy in (
            (-outline, 0),
            (outline, 0),
            (0, -outline),
            (0, outline),
            (-outline, -outline),
            (outline, outline),
            (-outline, outline),
            (outline, -outline),
        ):
            draw.text((tx + ox, ty + oy), text, font=font, fill=(0, 0, 0, 160))
        draw.text((tx, ty), text, font=font, fill=(255, 255, 255))

    return img.resize((size, size), resample=Image.Resampling.LANCZOS)


class TrayBatteryApp:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._info: BatteryInfo | None = None
        self._error: str | None = "正在读取…"
        self._icon_size = _tray_icon_px()
        self._icon = pystray.Icon(
            "ML702Battery",
            make_icon(None, size=self._icon_size),
            "ML702 电量",
            menu=self._build_menu(),
        )

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem(lambda item: self._status_text(), None, enabled=False),
            pystray.MenuItem("立即刷新", self._on_refresh),
            pystray.MenuItem("退出", self._on_quit),
        )

    def _status_text(self) -> str:
        if self._info is None:
            return self._error or "无数据"
        state = "充电中" if self._info.charging else "无线"
        return f"{self._info.percent}% · {self._info.millivolts} mV · {state}"

    def _apply(self, info: BatteryInfo | None, error: str | None) -> None:
        self._info = info
        self._error = error
        if info is None:
            self._icon.icon = make_icon(None, size=self._icon_size)
            self._icon.title = f"ML702: {error or '未知'}"
        else:
            self._icon.icon = make_icon(info.percent, info.charging, size=self._icon_size)
            state = "充电" if info.charging else "放电"
            self._icon.title = f"ML702 {info.percent}% ({state}, {info.millivolts} mV)"
        self._icon.update_menu()

    def _poll_once(self) -> None:
        try:
            # Active HID query (send 0x04, wait reply); not event-driven.
            info = read_battery(timeout_s=0.8, attempts=3)
            self._apply(info, None)
        except Exception as e:
            # Keep last good reading; only wipe icon if we never had one.
            if self._info is None:
                self._apply(None, str(e))
            else:
                self._error = f"查询失败，保留上次: {e}"
                self._icon.title = (
                    f"ML702 {self._info.percent}% "
                    f"(上次有效 · 重试中)"
                )
                self._icon.update_menu()

    def _on_refresh(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        threading.Thread(target=self._poll_once, daemon=True).start()

    def _on_quit(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        self._stop.set()
        icon.stop()

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._poll_once()
            # Wake early if user requested quit during wait
            self._stop.wait(POLL_SECONDS)

    def run(self) -> None:
        threading.Thread(target=self._loop, daemon=True).start()
        self._icon.run()


def main() -> None:
    _enable_dpi_awareness()
    TrayBatteryApp().run()


if __name__ == "__main__":
    main()
