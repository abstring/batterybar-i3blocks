#!/usr/bin/env python3
"""BatteryBar-like i3blocks block using only sysfs, Pango markup, and Python."""

from __future__ import annotations

import argparse
import html
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any


SYSFS = Path(os.environ.get("BATTERYBAR_SYSFS", "/sys/class/power_supply"))
CRITICAL = int(os.environ.get("BATTERYBAR_CRITICAL", "10"))
COLORS = {
    "green": os.environ.get("BATTERYBAR_GREEN", "#49C64B"),
    "red": os.environ.get("BATTERYBAR_RED", "#E44747"),
    "blue": os.environ.get("BATTERYBAR_BLUE", "#398BDB"),
    "empty": os.environ.get("BATTERYBAR_EMPTY", "#24282D"),
    "outline": os.environ.get("BATTERYBAR_OUTLINE", "#D8DEE9"),
}
FONT = os.environ.get("BATTERYBAR_FONT", "DejaVu Sans Mono 11")
CELLS = 9
RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", tempfile.gettempdir()))
RATE_FILE = RUNTIME_DIR / f"batterybar-{os.getuid()}-rate.json"


def read_text(path: Path) -> str | None:
    try:
        value = path.read_text(errors="replace").strip()
        return value or None
    except (OSError, UnicodeError):
        return None


def number(values: dict[str, str | None], key: str) -> float | None:
    try:
        return float(values[key]) if values.get(key) is not None else None
    except (TypeError, ValueError):
        return None


def discover() -> list[dict[str, Any]]:
    batteries: list[dict[str, Any]] = []
    try:
        paths = sorted(SYSFS.iterdir())
    except OSError:
        return batteries
    for path in paths:
        if not path.name.startswith("BAT") or read_text(path / "type") != "Battery":
            continue
        names = sorted(p.name for p in path.iterdir() if p.is_file())
        raw = {name: read_text(path / name) for name in names}
        if raw.get("present", "1") == "0":
            continue
        batteries.append({"name": path.name, "path": str(path.resolve()), "raw": raw})
    return batteries


def upower_estimate(expected_state: str) -> dict[str, Any]:
    """Use UPower's aggregate estimate only as a validated fallback."""
    if not shutil.which("upower"):
        return {"available": False}
    try:
        proc = subprocess.run(
            ["upower", "-i", "/org/freedesktop/UPower/devices/DisplayDevice"],
            capture_output=True, text=True, timeout=2, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"available": False}
    values: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        if ":" in line:
            key, value = line.strip().split(":", 1)
            values[key.strip().lower()] = value.strip()
    key = "time to empty" if expected_state == "Discharging" else "time to full" if expected_state == "Charging" else ""
    seconds = None
    raw = values.get(key) if key else None
    if raw:
        parts = raw.split()
        try:
            amount = float(parts[0])
            unit = parts[1].lower()
            seconds = round(amount * (3600 if unit.startswith("hour") else 60 if unit.startswith("minute") else 1))
        except (IndexError, ValueError):
            seconds = None
    limit = 48 * 3600 if expected_state == "Discharging" else 24 * 3600
    if seconds is not None and not (60 <= seconds <= limit):
        seconds = None
    return {"available": proc.returncode == 0, "raw": values, "seconds": seconds}


def normalized(battery: dict[str, Any]) -> dict[str, Any]:
    raw = battery["raw"]
    voltage = number(raw, "voltage_now") or number(raw, "voltage_avg")
    # Normalize everything to uWh/uW. Charge/current need voltage to convert.
    if number(raw, "energy_now") is not None:
        basis = "energy"
        now = number(raw, "energy_now")
        full = number(raw, "energy_full")
        design = number(raw, "energy_full_design")
        rate = number(raw, "power_now") or number(raw, "power_avg")
    elif voltage and number(raw, "charge_now") is not None:
        basis = "charge converted at present voltage"
        factor = voltage / 1_000_000.0
        now = number(raw, "charge_now") * factor
        full = number(raw, "charge_full")
        full = full * factor if full is not None else None
        design = number(raw, "charge_full_design")
        design = design * factor if design is not None else None
        amps = number(raw, "current_now") or number(raw, "current_avg")
        rate = amps * factor if amps is not None else None
    else:
        basis = "percentage only"
        now = full = design = rate = None
    return {
        **battery,
        "basis": basis,
        "now_uwh": now,
        "full_uwh": full,
        "design_uwh": design,
        "rate_uw": abs(rate) if rate is not None else None,
        "voltage_uv": voltage,
        "capacity": number(raw, "capacity"),
        "status": raw.get("status") or "Unknown",
    }


def smooth_rate(rate_uw: float | None, design_uwh: float | None, state: str, write: bool = True) -> float | None:
    """Reject near-zero rates and keep one bounded EMA value (never a growing log)."""
    if rate_uw is None or not math.isfinite(rate_uw):
        return None
    floor = max(100_000.0, (design_uwh or 0) / 100.0)  # 0.1 W or a 100-hour discharge.
    if rate_uw < floor:
        return None
    old: float | None = None
    try:
        data = json.loads(RATE_FILE.read_text())
        if data.get("state") == state and data.get("rate_uw") and data.get("rate_uw") > 0:
            old = float(data["rate_uw"])
    except (OSError, ValueError, TypeError):
        pass
    result = rate_uw if old is None or rate_uw / old > 4 or old / rate_uw > 4 else old * 0.65 + rate_uw * 0.35
    if write:
        try:
            RATE_FILE.write_text(json.dumps({"state": state, "rate_uw": round(result, 2)}) + "\n")
        except OSError:
            pass
    return result


def calculate(batteries: list[dict[str, Any]], smooth: bool = True) -> dict[str, Any]:
    bats = [normalized(b) for b in batteries]
    if not bats:
        return {"batteries": [], "status": "No battery", "percentage": None, "seconds": None, "estimate": None}
    statuses = {str(b["status"]).lower() for b in bats}
    if "charging" in statuses:
        status = "Charging"
    elif "discharging" in statuses:
        status = "Discharging"
    elif statuses <= {"full", "not charging"} and all((b["capacity"] or 0) >= 99 for b in bats):
        status = "Full"
    elif "not charging" in statuses:
        status = "Not charging"
    elif "full" in statuses:
        status = "Full"
    else:
        status = "Unknown"
    fulls = [b["full_uwh"] for b in bats]
    nows = [b["now_uwh"] for b in bats]
    if all(x is not None and x > 0 for x in fulls) and all(x is not None and x >= 0 for x in nows):
        total_full = sum(fulls)
        total_now = sum(nows)
        percentage = max(0.0, min(100.0, total_now / total_full * 100))
    else:
        total_full = total_now = None
        weights = [(b["capacity"], b["full_uwh"]) for b in bats if b["capacity"] is not None]
        weighted = [(p, w) for p, w in weights if w is not None and w > 0]
        percentage = sum(p * w for p, w in weighted) / sum(w for _, w in weighted) if weighted else (
            sum(p for p, _ in weights) / len(weights) if weights else None
        )
    rates = [b["rate_uw"] for b in bats]
    raw_rate = sum(rates) if rates and all(r is not None for r in rates) else None
    total_design = sum(b["design_uwh"] for b in bats if b["design_uwh"] is not None) or None
    rate = smooth_rate(raw_rate, total_design, status, smooth) if smooth else raw_rate
    seconds = None
    if rate and total_now is not None and total_full is not None:
        hours = total_now / rate if status == "Discharging" else (total_full - total_now) / rate if status == "Charging" else None
        limit = 48 if status == "Discharging" else 24
        if hours is not None and 1 / 60 <= hours <= limit:
            seconds = round(hours * 3600)
    upower = upower_estimate(status)
    if seconds is None:
        seconds = upower.get("seconds")
    estimate = format_time(seconds) if seconds is not None else None
    return {
        "batteries": bats, "status": status, "percentage": percentage, "seconds": seconds,
        "estimate": estimate, "total_now_uwh": total_now, "total_full_uwh": total_full,
        "total_design_uwh": total_design, "raw_rate_uw": raw_rate, "smoothed_rate_uw": rate, "upower": upower,
    }


def format_time(seconds: int | None) -> str | None:
    if seconds is None:
        return None
    minutes = max(0, int(round(seconds / 60)))
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def render(result: dict[str, Any]) -> dict[str, Any]:
    pct = result.get("percentage")
    status = result.get("status", "Unknown")
    if pct is None:
        label = "  ?  "
        fill_count = 0
        fill = COLORS["green"]
    else:
        label = "FULL" if status == "Full" else (result.get("estimate") or f"{round(pct):d}%")
        label = label.center(5)[:5]
        fill_count = CELLS if status == "Charging" else round(CELLS * pct / 100)
        fill = COLORS["blue"] if status == "Charging" else COLORS["red"] if pct < CRITICAL else COLORS["green"]
    start = (CELLS - len(label)) // 2
    chars = [" "] * CELLS
    chars[start:start + len(label)] = list(label)
    spans = []
    for index, char in enumerate(chars):
        background = fill if index < fill_count else COLORS["empty"]
        # Bright green takes black; blue/red and empty cells take white.
        foreground = "#0B0D0E" if background == COLORS["green"] else "#FFFFFF"
        # Single-quoted Pango attributes also avoid escaped quotes in i3blocks
        # 1.4's intentionally small JSON parser.
        spans.append(f"<span background='{background}' foreground='{foreground}'>{html.escape(char)}</span>")
    body = "".join(spans)
    outline = COLORS["outline"]
    markup = (
        f"<span font_desc='{html.escape(FONT, quote=True)}' foreground='{outline}'>▏</span>"
        f"<span font_desc='{html.escape(FONT, quote=True)}' underline='single' underline_color='{outline}' "
        f"overline='single' overline_color='{outline}'>{body}</span>"
        f"<span font_desc='{html.escape(FONT, quote=True)}' foreground='{outline}'>▕▐</span>"
    )
    urgent = bool(pct is not None and pct < CRITICAL and status == "Discharging")
    return {"full_text": markup, "short_text": label.strip(), "markup": "pango", "urgent": urgent}


def human(value: float | None, unit: str, divisor: float = 1.0, decimals: int = 2) -> str:
    return "unavailable" if value is None else f"{value / divisor:.{decimals}f} {unit}"


def popup_text(result: dict[str, Any]) -> str:
    lines = ["BATTERYBAR DETAILS", ""]
    pct = result.get("percentage")
    lines += [f"System state: {result['status']}", f"Combined charge: {pct:.1f}%" if pct is not None else "Combined charge: unavailable",
              f"Estimate: {result.get('estimate') or 'unavailable'}",
              f"UPower fallback: {'available' if result.get('upower', {}).get('available') else 'unavailable'}", ""]
    for b in result["batteries"]:
        r = b["raw"]
        health = b["full_uwh"] / b["design_uwh"] * 100 if b["full_uwh"] and b["design_uwh"] else None
        lines += [f"[{b['name']}]", f"Manufacturer: {r.get('manufacturer') or 'unavailable'}",
                  f"Model: {r.get('model_name') or 'unavailable'}", f"Chemistry/type: {r.get('technology') or r.get('type') or 'unavailable'}",
                  f"Serial number: {r.get('serial_number') or 'unavailable'}", f"State: {b['status']}",
                  f"Charge: {b['capacity']:.0f}%" if b["capacity"] is not None else "Charge: unavailable",
                  f"Current energy: {human(b['now_uwh'], 'Wh', 1_000_000)} ({b['basis']})",
                  f"Design capacity: {human(b['design_uwh'], 'Wh', 1_000_000)}",
                  f"Full-charge capacity: {human(b['full_uwh'], 'Wh', 1_000_000)}",
                  f"Battery health: {health:.1f}%" if health is not None else "Battery health: unavailable",
                  f"Cycle count: {r.get('cycle_count') or 'unavailable'}",
                  f"Voltage: {human(b['voltage_uv'], 'V', 1_000_000, 3)}",
                  f"Current/power draw: {human(b['rate_uw'], 'W', 1_000_000)}",
                  f"Temperature: {human(number(r, 'temp'), '°C', 10)}" if r.get("temp") else "Temperature: unavailable",
                  f"Native sysfs name: {b['name']}", f"Resolved device: {b['path']}", ""]
        known = {"manufacturer", "model_name", "technology", "type", "serial_number", "status", "capacity", "energy_now", "energy_full",
                 "energy_full_design", "charge_now", "charge_full", "charge_full_design", "cycle_count", "voltage_now", "voltage_avg",
                 "current_now", "current_avg", "power_now", "power_avg", "temp", "uevent", "present"}
        extras = [(k, v) for k, v in r.items() if k not in known and v is not None]
        if extras:
            lines.append("Other exposed sysfs properties:")
            lines.extend(f"  {k}: {v}" for k, v in extras)
            lines.append("")
    return "\n".join(lines)


def show_popup(result: dict[str, Any]) -> None:
    text = popup_text(result)
    detail_file = RATE_FILE.with_name("batterybar-details.txt")
    try:
        detail_file.write_text(text)
    except OSError:
        return
    if shutil.which("yad"):
        subprocess.Popen(["yad", "--text-info", "--title=Battery details", "--width=380", "--height=400",
                          "--center", "--wrap", "--margins=8", "--button=gtk-close:0", "--fontname=Monospace 9",
                          f"--filename={detail_file}"],
                         start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif shutil.which("zenity"):
        subprocess.Popen(["zenity", "--text-info", "--title=Battery details", "--width=380", "--height=400",
                          f"--filename={detail_file}"], start_new_session=True, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)


def handle_click(result: dict[str, Any]) -> None:
    button = os.environ.get("BLOCK_BUTTON")
    if button == "1":
        show_popup(result)
    elif button == "3":
        tool = next((x for x in ("xfce4-power-manager-settings", "gnome-power-statistics", "mate-power-statistics") if shutil.which(x)), None)
        if tool:
            subprocess.Popen([tool], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            show_popup(result)
    # Button 2 intentionally just reaches the render below: i3blocks updates immediately.


DEMOS = [
    ("83% discharging, 2:42", {"status": "Discharging", "percentage": 83, "estimate": "02:42"}),
    ("48% charging, 1:15", {"status": "Charging", "percentage": 48, "estimate": "01:15"}),
    ("7% discharging, 0:18", {"status": "Discharging", "percentage": 7, "estimate": "00:18"}),
    ("100% full", {"status": "Full", "percentage": 100, "estimate": None}),
    ("unknown estimate", {"status": "Discharging", "percentage": 61, "estimate": None}),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dump", "--debug", action="store_true", dest="dump")
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()
    if args.demo:
        for name, values in DEMOS:
            print(json.dumps({"demo": name, **render(values)}, ensure_ascii=False))
        return 0
    batteries = discover()
    result = calculate(batteries, smooth=not args.dump)
    if args.dump:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        print("\nPopup preview:\n" + popup_text(result))
        return 0
    handle_click(result)
    print(json.dumps(render(result), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
