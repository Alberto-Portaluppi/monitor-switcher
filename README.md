# Monitor Switcher

A KDE Plasma tray icon to turn a group of monitors on/off together (via
`kscreen-doctor`), without opening the Display Configuration window.

Works with any number of monitors on any Plasma/Wayland setup — outputs
and their names are detected at runtime via `kscreen-doctor`, nothing is
hardcoded to a specific model or GPU. One example use case: monitors with
two video inputs (e.g. shared between a desktop and a laptop) where you
want to disable the desktop's outputs while working from the laptop, so
its mouse/focus doesn't leak onto those screens.

## Usage

- **Tray icon**: starts automatically on login (`~/.config/autostart/`).
  **Left click**: toggle the selected group on/off.
  **Right click**: menu to check/uncheck which monitors belong to the
  group, pick the primary monitor, force a toggle, refresh the list
  (after plugging/unplugging something), or quit.
- **Keyboard shortcut**: `Meta+M` toggles the selected group instantly, no
  click needed (registered declaratively via
  `~/.local/share/applications/monitor-switcher-toggle.desktop`'s
  `X-KDE-Shortcuts`). Rebindable in System Settings → Shortcuts → search
  for "Toggle Work Monitors".
- **Terminal**: `python3 monitor_switcher.py --list` prints the current
  state of every monitor; `--toggle` does the same thing as the shortcut,
  headless.

Which monitors belong to the group — and which one is the primary monitor
(marked with ★ in the tray menu, under "Primary monitor") — is saved in
`~/.config/monitor-switcher/config.json` and can be changed entirely from
the tray menu; no need to touch the code. KWin tends to reshuffle output
priorities when outputs are disabled/re-enabled, so the saved primary is
re-applied on every toggle to keep it from drifting.

The `DEFAULT_SELECTED` / `DEFAULT_PRIMARY` constants at the top of
`monitor_switcher.py` only seed the very first run (using whatever
connector names `kscreen-doctor -o` reports on your machine, e.g.
`HDMI-A-1`, `DP-1`); after that, everything is driven by the config file
and the tray menu.

## Run manually / debug

```bash
python3 monitor_switcher.py            # show the tray icon
python3 monitor_switcher.py --list     # current state
python3 monitor_switcher.py --toggle   # toggle the saved group and exit
```

## Requirements

- `kscreen-doctor` (ships with Plasma)
- `PyQt6`
- `edid-decode` (optional, only used to resolve the monitor's commercial
  name; falls back to the connector name otherwise)

## Install

```bash
mkdir -p ~/.config/autostart ~/.local/share/applications

cat > ~/.config/autostart/monitor-switcher.desktop <<EOF
[Desktop Entry]
Type=Application
Name=Monitor Switcher
Comment=Tray icon to turn groups of monitors on/off
Exec=python3 "$PWD/monitor_switcher.py"
Icon=preferences-desktop-display-randr
Terminal=false
NoDisplay=true
X-GNOME-Autostart-enabled=true
EOF

cat > ~/.local/share/applications/monitor-switcher-toggle.desktop <<EOF
[Desktop Entry]
Type=Application
Name=Toggle Work Monitors
Comment=Turns the monitors selected in Monitor Switcher on/off
Exec=python3 "$PWD/monitor_switcher.py" --toggle
Icon=preferences-desktop-display-randr
Terminal=false
NoDisplay=true
X-KDE-Shortcuts=Meta+M
EOF

update-desktop-database ~/.local/share/applications
kbuildsycoca6
python3 monitor_switcher.py &
```

## License

MIT
