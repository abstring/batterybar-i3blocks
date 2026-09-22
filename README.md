# batterybar-i3blocks

A compact, system-level BatteryBar interpretation for stock i3bar/i3blocks.

<img width="676" height="24" alt="image" src="https://github.com/user-attachments/assets/d9e1d47d-3b7f-4651-b504-95f67ad58ee8" />

The Python script discovers all `BAT*` power supplies, combines compatible
measurements, calculates guarded time estimates, and renders a Pango-only
battery outline, fill, terminal, and centered label. Run `./batterybar.py
--demo` for representative JSON output or `./batterybar.py --dump` to inspect
the machine's raw and normalized battery values.

The installed i3blocks stanza uses JSON output (`format=json`), Pango markup,
a ten-second interval, and click events. Left click opens details, middle click
refreshes, and right click opens the installed power manager (or details).

## Installation

The block requires Python 3 and i3blocks. UPower is an optional source of
aggregate time estimates. YAD is preferred for the detail popup, with Zenity
as a fallback.

```sh
install -Dm755 batterybar.py "$HOME/.config/i3blocks/scripts/batterybar.py"
```

Copy the stanza from `i3blocks.conf` into the desired position in the user's
i3blocks configuration, then reload i3 in place with `i3-msg restart`. The
script discovers present `BAT*` devices at runtime; no device name or machine
path is configured.

## Customization

The defaults can be overridden in the block command's environment:

- `BATTERYBAR_CRITICAL` (default `10`)
- `BATTERYBAR_GREEN`, `BATTERYBAR_RED`, `BATTERYBAR_BLUE`
- `BATTERYBAR_EMPTY`, `BATTERYBAR_OUTLINE`
- `BATTERYBAR_FONT` (default `DejaVu Sans Mono 11`)
- `BATTERYBAR_SYSFS` (mainly useful for tests)

Change `interval` in the i3blocks stanza to adjust the refresh period. Popup
selection is automatic: YAD, then Zenity; right click tries common desktop
power settings tools and otherwise opens the detail popup.

Runtime smoothing and popup data are bounded files in `$XDG_RUNTIME_DIR`, or
the platform temporary directory when that variable is unavailable. Nothing
is written to the repository or the user's home directory.

## KDE Plasma 6 widget

`plasma/org.example.batterybar` is a native Plasma panel widget. It uses KDE's
battery model for percentage, charging state, and the smoothed remaining-time
estimate. The bar is green while discharging, blue while charging, and red
below 10%; it shows `HH:MM`, `FULL`, or a percentage when no estimate is
available. The compact bar has shaded edges for a rounded appearance. Left
click switches between `HH:MM` and percentage; right click opens the details
popup, and middle click repaints the bar. The label is dark over green fill and
light over the empty portion, including when a letter crosses the fill edge.
With two internal batteries, time mode keeps one bar with KDE's combined time
estimate; percentage mode draws two equal bars with each battery's own charge.
The panel slot remains 84 pixels wide in both modes. Peripheral batteries such
as headphones are excluded from the split view.

Install it for the current user with:

```sh
kpackagetool6 --type Plasma/Applet --install plasma/org.example.batterybar
```

Then open the panel's **Edit Mode**, choose **Add Widgets**, search for
**BatteryBar**, and drag it next to the clock on the right. To update an
existing installation, run `kpackagetool6 --type Plasma/Applet --upgrade
plasma/org.example.batterybar` and restart Plasma Shell or sign out and back
in. The original i3blocks implementation remains available separately.
