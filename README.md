# Vesim Configurator

A small Windows GUI for configuring the Vessel Specific Input Manager (Vesim) in
[Project Apollo - NASSP](https://github.com/orbiternassp/NASSP), the Apollo add-on for Orbiter.
Unofficial and not affiliated with the NASSP team. Format reference: `Doc/Project Apollo - NASSP/VESIM.txt`
in the NASSP repo.

Point it at your Orbiter folder (the one containing `Config\ProjectApollo`). It creates and edits the
Vesim `.launchpad.cfg` files for you, detects your joysticks, and has a Listen button and live monitor.

Run: `Vesim Configurator.bat`, or `pythonw vesim_configurator.py <path to Orbiter>`.
Needs Python 3 with Tkinter. Writes `<CSM|LM> - <device>.launchpad.cfg` into
`Config/ProjectApollo/Vesim`. All inputs are built into the tool, so no shipped files are required.

## One stick for rotation AND translation (with a toggle button)

Vesim reads the controllers differently depending on the Orbiter attitude mode:

| Mode | Rotation controller (CSM RHC / LM ACA) | Translation controller (CSM THC / LM TTCA) |
|---|---|---|
| Rotation | its own axes | its own axes |
| Translation | centred | **the rotation controller's axes** |

So for a single stick:

1. Bind only `RHC Roll/Pitch/Yaw` (CSM) or `ACA Roll/Pitch/Yaw` (LM) to the stick.
2. **Leave `THC X/Y/Z` / `TTCA X/Y/Z` empty.** If they share the stick's axes, one movement rotates
   *and* translates in rotation mode. The GUI shows such rows in orange.
3. Bind `Rotation/Translation toggle` to a button. Each press switches the stick between modes.

Notes (from reading the code, verify in-game):
- LM yaw is inverted for the ACA but not when it feeds translation, so yaw / the third translation
  axis can feel opposite. Reverse flips both modes.
- LM translation only works while the cockpit `LeftTTCATranslSwitch` is up.
- CSM translation mapping: roll -> THC Y, pitch -> Z, yaw -> X.

## Other things worth knowing

- Vesim sets up devices in order (Keyboard first). A device with no config file anywhere in its
  fallback chain stops setup of every device after it, so the tool creates missing blank files for
  the keyboard and attached sticks on startup / Rescan.
- Device names must match DirectInput exactly, including leading/trailing spaces
  (e.g. `" VKBSim Gunfighter MCG Ultimate "`). The tool never trims them.
- A key can drive only one input (the later row wins), and releasing one of two keys on the same axis
  resets the axis even if the other is held.
- Vesim does not consume keys or look at Shift/Ctrl: keys bound here still reach NASSP and Orbiter.
- Enabling Vesim disables the legacy `joystick.ini` RHC/THC settings and the numpad RHC keys.

## Axis direction

The Live Monitor shows raw values and does not apply Reverse. The sim also flips some axes itself, e.g. the
LM `TTCA Throttle` (raw 0 = full throttle). Test direction in-game before ticking Reverse.

## License

MIT, see `LICENSE`.
