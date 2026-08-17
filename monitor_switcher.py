#!/usr/bin/env python3
"""
Monitor Switcher
================
Turns a chosen group of monitors on/off in one shot (via kscreen-doctor),
without opening KDE's Display Configuration window.

Usage:
    monitor_switcher.py            -> show the tray icon (normal mode)
    monitor_switcher.py --toggle   -> toggle the selected group and exit
                                       (used by the global keyboard shortcut)
    monitor_switcher.py --list     -> print detected monitors (debug)

Which monitors belong to the group is stored in:
    ~/.config/monitor-switcher/config.json
and can be changed from the tray icon's menu (right click).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "monitor-switcher"
CONFIG_FILE = CONFIG_DIR / "config.json"

# Default selection on first run: the two work monitors (middle = DP-1
# "Hailstorm", right = DP-2 "LF24T450F"). The left one (HDMI-A-1, personal
# use) is left out by default. Changeable from the tray menu.
DEFAULT_SELECTED = ["DP-1", "DP-2"]

# Which output should always be the primary (priority 1) monitor. KWin
# tends to reshuffle output priorities when outputs are disabled/enabled,
# so this gets re-applied on every toggle. Changeable from the tray menu.
DEFAULT_PRIMARY = "DP-1"


# --------------------------------------------------------------------------
# kscreen-doctor helpers
# --------------------------------------------------------------------------

def get_outputs() -> list[dict]:
    """Return the list of connected outputs via `kscreen-doctor -j`."""
    try:
        out = subprocess.run(
            ["kscreen-doctor", "-j"], capture_output=True, text=True, check=True
        )
        data = json.loads(out.stdout)
    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error querying kscreen-doctor: {e}", file=sys.stderr)
        return []
    return [o for o in data.get("outputs", []) if o.get("connected")]


_edid_cache: dict[str, str] = {}


def friendly_name(output_name: str) -> str:
    """Try to get the monitor's commercial name (via EDID); falls back to
    the connector name (e.g. 'DP-1') if that fails."""
    if output_name in _edid_cache:
        return _edid_cache[output_name]

    result = output_name
    for edid_path in Path("/sys/class/drm").glob(f"card*-{output_name}/edid"):
        try:
            raw = edid_path.read_bytes()
            if not raw:
                continue
            decoded = subprocess.run(
                ["edid-decode"], input=raw, capture_output=True, timeout=5
            ).stdout.decode(errors="ignore")
            m = re.search(r"Display Product Name:\s*'([^']+)'", decoded)
            if m:
                result = m.group(1)
                break
        except (OSError, subprocess.SubprocessError):
            continue

    _edid_cache[output_name] = result
    return result


def apply_kscreen(commands: list[str]) -> bool:
    """Run a list of commands like 'output.DP-1.disable' in a single
    kscreen-doctor call."""
    if not commands:
        return True
    try:
        subprocess.run(["kscreen-doctor", *commands], check=True, capture_output=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"Error applying changes: {e}", file=sys.stderr)
        return False


def priority_commands(outputs: list[dict], primary_name: str) -> list[str]:
    """Build 'output.<name>.priority.<n>' commands that put `primary_name`
    at priority 1 (primary) and every other connected output right after
    it, in a stable order. Re-applying this on every toggle is what keeps
    the primary monitor from drifting when outputs get disabled/enabled."""
    names = {o["name"] for o in outputs}
    if primary_name not in names:
        return []
    rest = sorted((o for o in outputs if o["name"] != primary_name), key=lambda o: o["id"])
    ordered = [primary_name] + [o["name"] for o in rest]
    return [f"output.{n}.priority.{i + 1}" for i, n in enumerate(ordered)]


def compact_positions(remaining: list[dict]) -> list[str]:
    """kscreen/KWin refuses a layout with gaps between screens ("Spaces
    between screens are not supported"). When an output in the middle of
    the row gets disabled, slide whatever stays enabled so it keeps
    touching, left to right, without moving the leftmost one."""
    ordered = sorted(remaining, key=lambda o: o["pos"]["x"])
    commands = []
    cursor_x = ordered[0]["pos"]["x"] if ordered else 0
    for o in ordered:
        if o["pos"]["x"] != cursor_x:
            commands.append(f"output.{o['name']}.position.{cursor_x},{o['pos']['y']}")
        cursor_x += o["size"]["width"]
    return commands


def restore_positions(outputs: list[dict]) -> list[str]:
    """Move every output that has a saved position back to where it was
    the last time all monitors were enabled together."""
    layout = load_layout()
    commands = []
    for o in outputs:
        pos = layout.get(o["name"])
        if pos:
            commands.append(f"output.{o['name']}.position.{pos['x']},{pos['y']}")
    return commands


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

def load_config() -> dict:
    try:
        data = json.loads(CONFIG_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        data = {}
    if not isinstance(data.get("selected"), list):
        data["selected"] = list(DEFAULT_SELECTED)
    if not isinstance(data.get("primary"), str):
        data["primary"] = DEFAULT_PRIMARY
    return data


def save_config(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def load_selected() -> list[str]:
    return load_config()["selected"]


def save_selected(selected: list[str]) -> None:
    data = load_config()
    data["selected"] = selected
    save_config(data)


def load_primary() -> str:
    return load_config()["primary"]


def save_primary(name: str) -> None:
    data = load_config()
    data["primary"] = name
    save_config(data)


def load_layout() -> dict:
    layout = load_config().get("layout")
    return layout if isinstance(layout, dict) else {}


def save_layout(layout: dict) -> None:
    data = load_config()
    data["layout"] = layout
    save_config(data)


# --------------------------------------------------------------------------
# Toggle logic (shared between CLI mode and tray mode)
# --------------------------------------------------------------------------

def toggle_group(names: list[str]) -> tuple[bool, str]:
    """Turn a group of outputs on/off together. If any of them is enabled,
    disable them all; otherwise enable them all. Returns (success, message)."""
    outputs = get_outputs()
    by_name = {o["name"]: o for o in outputs}

    present = [n for n in names if n in by_name]
    if not present:
        return False, "None of the selected monitors is currently connected."

    group_enabled = any(by_name[n]["enabled"] for n in present)
    action = "disable" if group_enabled else "enable"

    commands = [f"output.{n}.{action}" for n in present]

    if action == "disable":
        remaining_on = [o for o in outputs if o["name"] not in present and o["enabled"]]
        # Safety: never leave the whole system with zero enabled monitors.
        if not remaining_on:
            return False, "Cancelled: this would turn off every monitor."
        # Snapshot the arrangement while it still has everyone in it, so it
        # can be restored later -- only while it's a "complete" layout.
        if all(o["enabled"] for o in outputs):
            save_layout({o["name"]: o["pos"] for o in outputs})
        # Close the gap the disabled output(s) would otherwise leave behind.
        commands += compact_positions(remaining_on)
    else:
        # Put everyone (the ones coming back and the ones that were
        # shifted to compact the gap) back where they started.
        commands += restore_positions(outputs)

    # Re-assert the primary monitor (and a stable priority order for the
    # rest) in the same atomic call, since KWin tends to reshuffle
    # priorities when outputs are disabled/enabled.
    commands += priority_commands(outputs, load_primary())
    ok = apply_kscreen(commands)
    verb = "turned off" if action == "disable" else "turned on"
    names_str = ", ".join(friendly_name(n) for n in present)
    if ok:
        return True, f"Monitors {verb}: {names_str}"
    return False, f"Failed to apply changes to: {names_str}"


# --------------------------------------------------------------------------
# CLI mode (used by the global keyboard shortcut, no GUI)
# --------------------------------------------------------------------------

def notify(title: str, message: str) -> None:
    try:
        subprocess.run(["notify-send", "-a", "Monitor Switcher", title, message], check=False)
    except FileNotFoundError:
        pass


def cli_toggle() -> int:
    selected = load_selected()
    ok, msg = toggle_group(selected)
    notify("Monitor Switcher", msg)
    print(msg)
    return 0 if ok else 1


def cli_list() -> int:
    primary = load_primary()
    for o in get_outputs():
        state = "on" if o["enabled"] else "off"
        tag = " (primary)" if o["name"] == primary else ""
        print(f"{o['name']:10s} {friendly_name(o['name']):20s} {state}{tag}")
    return 0


# --------------------------------------------------------------------------
# Tray mode (GUI)
# --------------------------------------------------------------------------

def run_tray() -> int:
    from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
    from PyQt6.QtGui import QIcon, QAction, QActionGroup

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    icon = QIcon.fromTheme("preferences-desktop-display-randr")
    tray = QSystemTrayIcon(icon, app)
    tray.setToolTip("Monitor Switcher")

    menu = QMenu()
    selected = set(load_selected())
    primary = load_primary()
    monitor_actions: dict[str, QAction] = {}

    def rebuild_menu():
        menu.clear()
        monitor_actions.clear()
        outputs = get_outputs()

        header = menu.addAction("Monitors in the group (click to toggle):")
        header.setEnabled(False)

        for o in outputs:
            name = o["name"]
            label = friendly_name(name)
            state = "on" if o["enabled"] else "off"
            star = " ★" if name == primary else ""
            act = QAction(f"{label} ({state}){star}", menu, checkable=True)
            act.setChecked(name in selected)
            act.toggled.connect(lambda checked, n=name: on_monitor_toggled(n, checked))
            menu.addAction(act)
            monitor_actions[name] = act

        menu.addSeparator()
        toggle_action = menu.addAction("Toggle selected now")
        toggle_action.triggered.connect(do_toggle)

        menu.addSeparator()
        primary_menu = menu.addMenu("Primary monitor (★)")
        primary_group = QActionGroup(primary_menu)
        primary_group.setExclusive(True)
        for o in outputs:
            name = o["name"]
            act = QAction(friendly_name(name), primary_menu, checkable=True)
            act.setChecked(name == primary)
            act.triggered.connect(lambda checked, n=name: on_primary_changed(n))
            primary_group.addAction(act)
            primary_menu.addAction(act)

        menu.addSeparator()
        refresh_action = menu.addAction("Refresh monitor list")
        refresh_action.triggered.connect(rebuild_menu)

        menu.addSeparator()
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(app.quit)

        update_tooltip(outputs)

    def on_monitor_toggled(name: str, checked: bool):
        if checked:
            selected.add(name)
        else:
            selected.discard(name)
        save_selected(sorted(selected))

    def on_primary_changed(name: str):
        nonlocal primary
        primary = name
        save_primary(name)
        apply_kscreen(priority_commands(get_outputs(), name))
        rebuild_menu()

    def update_tooltip(outputs=None):
        outputs = outputs if outputs is not None else get_outputs()
        by_name = {o["name"]: o for o in outputs}
        present = [n for n in selected if n in by_name]
        if not present:
            tray.setToolTip("Monitor Switcher — no monitor selected")
            return
        state = "on" if any(by_name[n]["enabled"] for n in present) else "off"
        names_str = ", ".join(friendly_name(n) for n in present)
        tray.setToolTip(f"Monitor Switcher\n{names_str}: {state}")

    def do_toggle():
        ok, msg = toggle_group(sorted(selected))
        tray.showMessage("Monitor Switcher", msg, icon, 3000)
        rebuild_menu()

    tray.setContextMenu(menu)
    rebuild_menu()

    def on_activated(reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            do_toggle()

    tray.activated.connect(on_activated)
    tray.show()

    return app.exec()


def main() -> int:
    if "--toggle" in sys.argv:
        return cli_toggle()
    if "--list" in sys.argv:
        return cli_list()
    return run_tray()


if __name__ == "__main__":
    sys.exit(main())
