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

kscreen/KWin also refuses a layout with a gap between screens, which
happens if you disable a monitor sitting between two others. To avoid
that, the app snapshots the current arrangement (`layout` in the config
file) whenever every monitor is enabled, slides the remaining ones
together to close the gap when one turns off, and moves everything back
to its saved spot when it turns back on.

The `DEFAULT_SELECTED` / `DEFAULT_PRIMARY` constants at the top of
`monitor_switcher.py` only seed the very first run (using whatever
connector names `kscreen-doctor -o` reports on your machine, e.g.
`HDMI-A-1`, `DP-1`); after that, everything is driven by the config file
and the tray menu.

### Switching the monitor's physical input too (optional)

If a monitor is shared with another machine over a second cable (e.g. a
laptop on HDMI, this PC on DisplayPort), `kscreen-doctor` can only turn
this PC's *output* off — it can't touch which cable the monitor is
actually displaying. That part is a separate protocol, DDC/CI (the same
channel KDE uses for hardware brightness control), and needs
[`ddcutil`](https://www.ddcutil.com/) installed (`sudo apt install
ddcutil`).

When a monitor's connector name is listed in `INPUT_SOURCE_CODES` at the
top of `monitor_switcher.py`, toggling it off also flips its input to the
other machine's cable, and toggling it back on claims it back — so
turning the group off both stops this PC's mouse/focus from reaching it
*and* hands the screen to the other machine, and turning it back on
brings both back together.

The codes are painfully monitor-specific: **don't trust `ddcutil
capabilities`** — on at least one panel here its advertised codes (the
standard MCCS `0x0f`/`0x11`/`0x12`) did nothing, while the real,
manufacturer-specific codes it actually responds to (`0x07`/`0x05`, found
by trial and error) worked fine. To find yours:

```bash
ddcutil detect                    # lists each monitor's /dev/i2c-N bus
ddcutil --bus N getvcp 60         # reads the *current* input's real code
                                   # (switch inputs by hand between reads
                                   # to map out which code is which)
ddcutil --bus N setvcp 60 0xXX    # try writing a candidate code
```

This is best-effort by design: if `ddcutil` isn't installed, a monitor
has no entry in `INPUT_SOURCE_CODES`, or a DDC/CI write fails, the KWin
enable/disable still happens normally — nothing here can block that.

**Watch out for one-way monitors.** Some panels power down their
DisplayPort DDC/CI responder entirely once DisplayPort stops being the
*selected* input — HDMI's simpler DDC pins tend to survive this, DP's AUX
channel often doesn't. That makes switching *away* from DisplayPort work
fine, but switching *back* impossible: by the time you'd send that
command, the channel driving it is already dead, and no retry, link
retrain, alternate `/dev/i2c-*` bus, or USB fallback brings it back — only
the monitor's own physical button does. Confirm both directions actually
round-trip (switch away, then back, with a real signal on the other
input) before adding a monitor to `INPUT_SOURCE_CODES` — a one-way entry
will silently strand that monitor on the other machine's input every
time you turn it back on.

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
- `ddcutil` (optional, only needed for the physical input-switching
  feature described below)

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
