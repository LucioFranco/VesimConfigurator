#!/usr/bin/env python
"""
Vesim Configurator - a GUI for NASSP's Vessel Specific Input Manager.

Vesim maps virtual spacecraft inputs (RHC/THC axes, DSKY keys, switches ...) to
joystick axes/buttons/POV hats/sliders or keyboard keys. The mapping lives in
tab-delimited files in  <Orbiter>\\Config\\ProjectApollo\\Vesim :

    <vessel> - <device>.cfg             shipped defaults (do not edit)
    <vessel> - <device>.launchpad.cfg   user settings   (this tool writes these)

where <vessel> is CSM or LM and <device> is the joystick name exactly as
DirectInput reports it, "GenericJoystick" or "Keyboard".  The format is
documented in Doc\\Project Apollo - NASSP\\VESIM.txt.

Pure standard library (Tkinter + ctypes/winmm for live joystick detection).
"""
import ctypes
import os
import re
import shutil
import sys
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_TITLE = "NASSP Vesim Configurator"
VESSELS = ["CSM", "LM"]
KEYBOARD = "Keyboard"
GENERIC = "GenericJoystick"
CFG_EXT = ".cfg"
USER_EXT = ".launchpad.cfg"
HEADER = ["INPUT", "INPUTTYPE", "SUBDEVID", "REVERSE", "MODIFIER"]
PA_REL = os.path.join("Config", "ProjectApollo")
VESIM_REL = os.path.join(PA_REL, "Vesim")
FLAG_REL = os.path.join("Config", "ProjectApollo", "Saturn5.launchpad.cfg")

AXES = ["X", "Y", "Z", "RX", "RY", "RZ"]
SLIDERS = ["0", "1"]
POVS = ["0H", "0V", "1H", "1V", "2H", "2V", "3H", "3V"]
BUTTONS = [str(i) for i in range(128)]
JOY_KINDS = ["Axis", "Slider", "POV", "Button"]
JOY_VALUES = {"Axis": AXES, "Slider": SLIDERS, "POV": POVS, "Button": BUTTONS}

# Key names exactly as vesim.cpp's keydata[] table spells them.
KEYS = (["Escape"] + list("1234567890") + ["-", "=", "Backspace", "Tab"]
        + list("QWERTYUIOP") + ["{", "}", "Enter", "LCtrl"] + list("ASDFGHJKL")
        + [";", "'", "`", "LShift", "\\"] + list("ZXCVBNM")
        + [",", ".", "/", "RShift", "Keypad *", "LAlt", "Space", "Caps Lock"]
        + ["F%d" % i for i in range(1, 11)]
        + ["Num Lock", "Scroll Lock", "Keypad 7", "Keypad 8", "Keypad 9", "Keypad -",
           "Keypad 4", "Keypad 5", "Keypad 6", "Keypad +", "Keypad 1", "Keypad 2",
           "Keypad 3", "Keypad 0", "Keypad .", "OEM 102", "F11", "F12", "Keypad Enter",
           "RCtrl", "Keypad /", "SysReq", "RAlt", "Pause", "Home", "Up", "Page Up",
           "Left", "Right", "End", "Down", "Page Down", "Insert", "Delete"])
KEYS_LOWER = {k.lower(): k for k in KEYS}

TK_KEYSYMS = {
    "Escape": "Escape", "BackSpace": "Backspace", "Tab": "Tab", "Return": "Enter",
    "Control_L": "LCtrl", "Control_R": "RCtrl", "Shift_L": "LShift", "Shift_R": "RShift",
    "Alt_L": "LAlt", "Alt_R": "RAlt", "space": "Space", "Caps_Lock": "Caps Lock",
    "Num_Lock": "Num Lock", "Scroll_Lock": "Scroll Lock", "Pause": "Pause",
    "Print": "SysReq", "Home": "Home", "Up": "Up", "Prior": "Page Up", "Left": "Left",
    "Right": "Right", "End": "End", "Down": "Down", "Next": "Page Down",
    "Insert": "Insert", "Delete": "Delete", "KP_Enter": "Keypad Enter",
    "KP_Multiply": "Keypad *", "KP_Subtract": "Keypad -", "KP_Add": "Keypad +",
    "KP_Decimal": "Keypad .", "KP_Divide": "Keypad /", "minus": "-", "equal": "=",
    "bracketleft": "{", "bracketright": "}", "semicolon": ";", "apostrophe": "'",
    "grave": "`", "backslash": "\\", "comma": ",", "period": ".", "slash": "/",
}
for _i in range(10):
    TK_KEYSYMS["KP_%d" % _i] = "Keypad %d" % _i
for _i in range(1, 13):
    TK_KEYSYMS["F%d" % _i] = "F%d" % _i


def keysym_to_name(keysym):
    if keysym in TK_KEYSYMS:
        return TK_KEYSYMS[keysym]
    if len(keysym) == 1 and keysym.upper() in KEYS_LOWER.values():
        return keysym.upper()
    return KEYS_LOWER.get(keysym.lower())


# ----------------------------------------------------------------------------
# Built-in catalog: every virtual input each vessel exposes, so the GUI never
# depends on the shipped .cfg files being present. Mirrors vesim_csm_inputs[]
# in src_csm/saturn.cpp and vesim_lm_inputs[] in src_lm/LEM.cpp. If NASSP adds
# inputs, add them here (the GUI still shows unknown rows found in a file).
# ----------------------------------------------------------------------------

def _dsky(prefix):
    keys = ["PRO", "KEY REL", "VERB", "NOUN", "ENTR", "CLR", "+", "-", "RSET"]
    keys += ["Number %d" % i for i in range(10)]
    return [("%s %s" % (prefix, k), "Button") for k in keys]


CATALOG = {
    "CSM": ([("RHC Roll", "Axis"), ("RHC Pitch", "Axis"), ("RHC Yaw", "Axis"),
             ("THC X", "Axis"), ("THC Y", "Axis"), ("THC Z", "Axis"),
             ("THC Move CCW", "Button"), ("THC Move CW", "Button"),
             ("Rotation/Translation toggle", "Button")]
            + _dsky("Main DSKY") + _dsky("LEB DSKY")
            + [("Direct Ullage", "Button"), ("Thrust On", "Button"),
               ("DV Thrust A Norm", "Button"), ("DV Thrust A Off", "Button"),
               ("DV Thrust B Norm", "Button"), ("DV Thrust B Off", "Button")]),
    "LM": ([("ACA Roll", "Axis"), ("ACA Pitch", "Axis"), ("ACA Yaw", "Axis"),
            ("TTCA X", "Axis"), ("TTCA Y", "Axis"), ("TTCA Z", "Axis"),
            ("Rotation/Translation toggle", "Button"), ("TTCA Throttle", "Axis"),
            ("Engine Start toggle", "Button"), ("Engine Stop toggle", "Button"),
            ("Descent Rate plus", "Button"), ("Descent Rate minus", "Button"),
            ("Abort toggle", "Button"), ("Abort Stage toggle", "Button"),
            ("Abort Stage Guard toggle", "Button")]
           + _dsky("DSKY")
           + [("Mode Control PGNS Auto/Att Hold toggle", "Button"),
              ("Mode Control PGNS Auto", "Button"), ("Mode Control PGNS Att Hold", "Button"),
              ("Mode Control PGNS Off", "Button"), ("TTCA Throttle/Jets Select lever", "Axis")]),
}

# Rotation controller axes vs translation controller axes. Vesim feeds the rotation
# axes to the translation controller when the Rotation/Translation toggle is in
# translation mode, so ONE stick can do both: bind only the rotation axes, leave the
# translation axes empty and bind the toggle button.
AXIS_GROUPS = {
    "CSM": (("RHC Roll", "RHC Pitch", "RHC Yaw"), ("THC X", "THC Y", "THC Z")),
    "LM": (("ACA Roll", "ACA Pitch", "ACA Yaw"), ("TTCA X", "TTCA Y", "TTCA Z")),
}
TOGGLE = "Rotation/Translation toggle"
TIP_SINGLE = ("One stick for rotation AND translation: bind only the %s axes, leave the %s axes "
              "empty, and bind this toggle to a button. Each press switches the stick between "
              "rotation and translation mode.")


def default_rows(vessel, device):
    """Blank starting rows for a device: every input listed, nothing mapped."""
    return [(n, t, Binding()) for n, t in CATALOG.get(vessel, [])]


# ----------------------------------------------------------------------------
# Model: reading / writing the config files
# ----------------------------------------------------------------------------

class Binding(object):
    """One row of a config file: input -> subdevice. subdev == '' means unmapped."""

    def __init__(self, subdev="", reverse=False, modifier=""):
        self.subdev = subdev
        self.reverse = reverse
        self.modifier = modifier

    def mapped(self):
        return self.subdev.strip() != ""


def parse_subdev(text, keyboard):
    """Return (kind, value) if Vesim would accept this SUBDEVID, else None."""
    text = text.strip()
    if keyboard:
        k = KEYS_LOWER.get(text.lower())
        return ("Key", k) if k else None
    m = re.match(r"^(axis|slider|pov|button)\s*(\S+)$", text, re.I)
    if not m:
        return None
    kind = m.group(1).capitalize() if m.group(1).lower() != "pov" else "POV"
    value = m.group(2).upper()
    if value in JOY_VALUES[kind]:
        return (kind, value)
    return None


def compose_subdev(kind, value):
    if kind == "Key":
        return value
    return "%s %s" % (kind, value)


def read_cfg(path):
    """Parse a Vesim cfg -> list of (input, type, Binding)."""
    rows = []
    with open(path, "r", encoding="latin-1", newline="") as f:
        lines = f.read().splitlines()
    if not lines:
        return rows
    header = [h.strip().upper() for h in lines[0].split("\t")]
    col = {h: i for i, h in enumerate(header)}
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.split("\t")

        def get(name):
            i = col.get(name)
            return parts[i].strip() if i is not None and i < len(parts) else ""

        name = parts[col.get("INPUT", 0)].strip() if parts else ""
        if not name:
            continue
        rows.append((name, get("INPUTTYPE"),
                     Binding(get("SUBDEVID"), get("REVERSE").lower() == "true", get("MODIFIER"))))
    return rows


def write_cfg(path, rows):
    """rows: list of (input, type, Binding). Writes CRLF like the shipped files."""
    out = ["\t".join(HEADER)]
    for name, typ, b in rows:
        if b.mapped():
            out.append("\t".join([name, typ, b.subdev, "TRUE" if b.reverse else "FALSE", b.modifier]))
        else:
            out.append("\t".join([name, typ, "", "", ""]))
    if os.path.exists(path) and not os.path.exists(path + ".bak"):
        shutil.copyfile(path, path + ".bak")
    with open(path, "w", encoding="latin-1", newline="") as f:
        f.write("\r\n".join(out) + "\r\n")


def cfg_path(vesim_dir, vessel, device, user):
    return os.path.join(vesim_dir, "%s - %s%s" % (vessel, device, USER_EXT if user else CFG_EXT))


def load_chain(vesim_dir, vessel, device):
    """Mimic Vesim's fallback order. Returns (path, rows) or (None, [])."""
    chain = [cfg_path(vesim_dir, vessel, device, True)]
    if device != KEYBOARD:
        chain.append(cfg_path(vesim_dir, vessel, GENERIC, True))
    chain.append(cfg_path(vesim_dir, vessel, device, False))
    if device != KEYBOARD:
        chain.append(cfg_path(vesim_dir, vessel, GENERIC, False))
    for p in chain:
        if os.path.isfile(p):
            try:
                return p, read_cfg(p)
            except OSError:
                pass
    return None, []


def default_chain(vesim_dir, vessel, device):
    chain = [cfg_path(vesim_dir, vessel, device, False)]
    if device != KEYBOARD:
        chain.append(cfg_path(vesim_dir, vessel, GENERIC, False))
    for p in chain:
        if os.path.isfile(p):
            return p, read_cfg(p)
    return None, []


def known_devices(vesim_dir, vessel):
    names = set()
    try:
        for fn in os.listdir(vesim_dir):
            for ext in (USER_EXT, CFG_EXT):
                prefix = vessel + " - "
                if fn.startswith(prefix) and fn.endswith(ext):
                    names.add(fn[len(prefix):-len(ext)])
                    break
    except OSError:
        pass
    return names


def find_orbiter_root():
    here = os.path.dirname(os.path.abspath(__file__))
    cur = here
    for _ in range(6):
        if os.path.isdir(os.path.join(cur, PA_REL)):
            return cur
        nxt = os.path.dirname(cur)
        if nxt == cur:
            break
        cur = nxt
    return ""


def read_flag(root):
    p = os.path.join(root, FLAG_REL)
    try:
        with open(p, "r", encoding="latin-1") as f:
            for line in f:
                m = re.match(r"^\s*JOYSTICK_VESIM\s+(\d+)", line, re.I)
                if m:
                    return m.group(1) != "0"
    except OSError:
        pass
    return False


def write_flag(root, enabled):
    p = os.path.join(root, FLAG_REL)
    lines = []
    if os.path.isfile(p):
        with open(p, "r", encoding="latin-1", newline="") as f:
            lines = f.read().splitlines()
    new = "JOYSTICK_VESIM %d" % (1 if enabled else 0)
    for i, line in enumerate(lines):
        if re.match(r"^\s*JOYSTICK_VESIM\b", line, re.I):
            lines[i] = new
            break
    else:
        lines.append(new)
    with open(p, "w", encoding="latin-1", newline="") as f:
        f.write("\r\n".join(lines) + "\r\n")


# ----------------------------------------------------------------------------
# Live joystick access through the legacy winmm API
# ----------------------------------------------------------------------------

class JOYINFOEX(ctypes.Structure):
    _fields_ = [(n, ctypes.c_uint32) for n in (
        "dwSize", "dwFlags", "dwXpos", "dwYpos", "dwZpos", "dwRpos", "dwUpos", "dwVpos",
        "dwButtons", "dwButtonNumber", "dwPOV", "dwReserved1", "dwReserved2")]


class JOYCAPSW(ctypes.Structure):
    _fields_ = ([("wMid", ctypes.c_uint16), ("wPid", ctypes.c_uint16),
                 ("szPname", ctypes.c_wchar * 32)]
                + [(n, ctypes.c_uint32) for n in (
                    "wXmin", "wXmax", "wYmin", "wYmax", "wZmin", "wZmax", "wNumButtons",
                    "wPeriodMin", "wPeriodMax", "wRmin", "wRmax", "wUmin", "wUmax",
                    "wVmin", "wVmax", "wCaps", "wMaxAxes", "wNumAxes", "wMaxButtons")]
                + [("szRegKey", ctypes.c_wchar * 32), ("szOEMVxD", ctypes.c_wchar * 260)])


# winmm axis -> Vesim/DirectInput axis name. winmm exposes X,Y,Z,R,U,V; DirectInput
# calls them X,Y,Z,Rx,Ry,Rz. The R/U/V <-> Rx/Ry/Rz pairing depends on the driver,
# so this is a best guess; the editor lets the user correct it and the live
# monitor shows which physical control moves which winmm axis.
WINMM_AXES = [("dwXpos", "X"), ("dwYpos", "Y"), ("dwZpos", "Z"),
              ("dwUpos", "RX"), ("dwVpos", "RY"), ("dwRpos", "RZ")]


def _oem_name(caps):
    """DirectInput's product name lives in the registry under the VID/PID key."""
    try:
        import winreg
        key = r"System\CurrentControlSet\Control\MediaProperties\PrivateProperties\Joystick\OEM\VID_%04X&PID_%04X" % (
            caps.wMid, caps.wPid)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            return winreg.QueryValueEx(k, "OEMName")[0]
    except Exception:
        return caps.szPname


class Joysticks(object):
    def __init__(self):
        try:
            self.winmm = ctypes.windll.winmm
        except Exception:
            self.winmm = None

    def list(self):
        """-> list of (winmm_id, directinput_style_name) currently connected."""
        found = []
        if not self.winmm:
            return found
        for i in range(16):
            caps = JOYCAPSW()
            if self.winmm.joyGetDevCapsW(i, ctypes.byref(caps), ctypes.sizeof(caps)) != 0:
                continue
            if self.read(i) is None:
                continue
            found.append((i, _oem_name(caps)))
        return found

    def read(self, jid):
        """-> dict(axes={name:0..65535}, buttons=int mask, pov=int) or None."""
        if not self.winmm:
            return None
        info = JOYINFOEX()
        info.dwSize = ctypes.sizeof(info)
        info.dwFlags = 0xFF  # JOY_RETURNALL
        if self.winmm.joyGetPosEx(jid, ctypes.byref(info)) != 0:
            return None
        return {"axes": {nm: getattr(info, f) & 0xFFFF for f, nm in WINMM_AXES},
                "buttons": info.dwButtons, "pov": info.dwPOV & 0xFFFF}


# ----------------------------------------------------------------------------
# GUI
# ----------------------------------------------------------------------------

class App(object):
    def __init__(self, root_win, orbiter_root):
        self.win = root_win
        self.joys = Joysticks()
        self.orbiter = orbiter_root
        self.dirty = False
        self.rows = []            # flat list of [name, type, Binding]; one per binding
        self.iid_row = {}         # tree iid -> row index
        self.loaded_from = None
        self.listening = None
        self.editing = False      # suppress editor callbacks while we fill widgets

        self.vessel = tk.StringVar(value=VESSELS[0])
        self.device = tk.StringVar(value=GENERIC)
        self.flt = tk.StringVar()
        self.only_mapped = tk.BooleanVar(value=False)
        self.vesim_on = tk.BooleanVar(value=False)
        self.kind = tk.StringVar()
        self.value = tk.StringVar()
        self.reverse = tk.BooleanVar(value=False)
        self.status = tk.StringVar()
        self.hint = tk.StringVar()

        self.build()
        self.set_orbiter(orbiter_root, initial=True)
        self.win.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---- layout -----------------------------------------------------------
    def build(self):
        w = self.win
        w.title(APP_TITLE)
        w.geometry("1060x680")
        w.minsize(900, 560)

        top = ttk.Frame(w, padding=(10, 8, 10, 4))
        top.pack(fill="x")
        ttk.Label(top, text="Vessel:").grid(row=0, column=0, sticky="w")
        for i, v in enumerate(VESSELS):
            ttk.Radiobutton(top, text=v, value=v, variable=self.vessel,
                            command=self.on_target_change).grid(row=0, column=1 + i, padx=2)
        ttk.Label(top, text="Device:").grid(row=0, column=3, padx=(18, 4))
        self.dev_cb = ttk.Combobox(top, textvariable=self.device, width=42)
        self.dev_cb.grid(row=0, column=4, sticky="we")
        self.dev_cb.bind("<<ComboboxSelected>>", lambda e: self.on_target_change())
        self.dev_cb.bind("<Return>", lambda e: self.on_target_change())
        ttk.Button(top, text="Rescan", command=self.rescan).grid(row=0, column=5, padx=6)
        ttk.Checkbutton(top, text="Enable Vesim in NASSP", variable=self.vesim_on,
                        command=self.on_flag).grid(row=0, column=6, padx=(18, 0))
        top.columnconfigure(4, weight=1)

        path = ttk.Frame(w, padding=(10, 0, 10, 4))
        path.pack(fill="x")
        self.root_lbl = ttk.Label(path, foreground="#555")
        self.root_lbl.pack(side="left")
        ttk.Button(path, text="Change Orbiter folder...", command=self.pick_root).pack(side="right")
        ttk.Button(path, text="Open config folder", command=self.open_folder).pack(side="right", padx=6)

        nb = ttk.Notebook(w)
        nb.pack(fill="both", expand=True, padx=10, pady=4)
        self.nb = nb
        tab_map = ttk.Frame(nb)
        tab_live = ttk.Frame(nb)
        nb.add(tab_map, text="  Mappings  ")
        nb.add(tab_live, text="  Live monitor  ")
        self.build_mappings(tab_map)
        self.build_live(tab_live)

        bar = ttk.Frame(w, padding=(10, 4, 10, 8))
        bar.pack(fill="x")
        ttk.Label(bar, textvariable=self.status, foreground="#333").pack(side="left")
        ttk.Button(bar, text="Save", command=self.save).pack(side="right")
        ttk.Button(bar, text="Clear all bindings", command=self.reset_defaults).pack(side="right", padx=6)
        ttk.Button(bar, text="Create files for all devices", command=self.create_all_devices).pack(side="left", padx=(14, 4))
        ttk.Button(bar, text="Clear all Vesim files...", command=self.clear_all_files).pack(side="left")
        ttk.Button(bar, text="Copy from...", command=self.copy_from).pack(side="right")

    def build_mappings(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        f = ttk.Frame(parent, padding=(0, 6, 0, 4))
        f.grid(row=0, column=0, columnspan=2, sticky="we")
        ttk.Label(f, text="Filter:").pack(side="left")
        e = ttk.Entry(f, textvariable=self.flt, width=24)
        e.pack(side="left", padx=4)
        self.flt.trace("w", lambda *a: self.fill_tree())
        ttk.Checkbutton(f, text="Mapped only", variable=self.only_mapped,
                        command=self.fill_tree).pack(side="left", padx=10)

        cols = ("input", "type", "binding", "reverse")
        tv = ttk.Treeview(parent, columns=cols, show="headings", selectmode="browse")
        for c, t, wd in (("input", "Virtual input", 280), ("type", "Type", 70),
                         ("binding", "Mapped to", 170), ("reverse", "Reverse", 60)):
            tv.heading(c, text=t)
            tv.column(c, width=wd, anchor="w" if c in ("input", "binding") else "center")
        sb = ttk.Scrollbar(parent, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        tv.grid(row=1, column=0, sticky="nsew")
        sb.grid(row=1, column=1, sticky="ns")
        tv.tag_configure("unmapped", foreground="#888")
        tv.tag_configure("bad", foreground="#c00000")
        tv.tag_configure("warn", foreground="#b36b00")
        tv.bind("<<TreeviewSelect>>", self.on_select)
        self.tv = tv

        ed = ttk.LabelFrame(parent, text="Selected input", padding=10)
        ed.grid(row=1, column=2, sticky="ns", padx=(10, 0))
        self.sel_lbl = ttk.Label(ed, text="(select a row)", font=("Segoe UI", 10, "bold"),
                                 wraplength=250)
        self.sel_lbl.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Label(ed, text="Control type").grid(row=1, column=0, sticky="w")
        self.kind_cb = ttk.Combobox(ed, textvariable=self.kind, state="readonly", width=14)
        self.kind_cb.grid(row=1, column=1, sticky="we", pady=2)
        self.kind_cb.bind("<<ComboboxSelected>>", self.on_kind)
        ttk.Label(ed, text="Control").grid(row=2, column=0, sticky="w")
        self.value_cb = ttk.Combobox(ed, textvariable=self.value, state="readonly", width=14)
        self.value_cb.grid(row=2, column=1, sticky="we", pady=2)
        self.value_cb.bind("<<ComboboxSelected>>", self.on_value)
        self.rev_chk = ttk.Checkbutton(ed, text="Reverse", variable=self.reverse, command=self.on_value)
        self.rev_chk.grid(row=3, column=0, columnspan=2, sticky="w", pady=4)
        self.listen_btn = ttk.Button(ed, text="Listen... (move / press)", command=self.start_listen)
        self.listen_btn.grid(row=4, column=0, columnspan=2, sticky="we", pady=(6, 2))
        self.add_btn = ttk.Button(ed, text="Add another binding", command=self.add_binding)
        self.add_btn.grid(row=5, column=0, columnspan=2, sticky="we", pady=2)
        self.clear_btn = ttk.Button(ed, text="Clear this binding", command=self.clear_binding)
        self.clear_btn.grid(row=6, column=0, columnspan=2, sticky="we", pady=2)
        ttk.Label(ed, textvariable=self.hint, wraplength=250, foreground="#555",
                  justify="left").grid(row=7, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ed.columnconfigure(1, weight=1)
        self.set_editor_enabled(False)

    def build_live(self, parent):
        top = ttk.Frame(parent, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="Connected controller:").pack(side="left")
        self.live_var = tk.StringVar()
        self.live_cb = ttk.Combobox(top, textvariable=self.live_var, state="readonly", width=50)
        self.live_cb.pack(side="left", padx=6)
        ttk.Label(top, text="Wiggle a control to see which axis / button it is.",
                  foreground="#555").pack(side="left", padx=10)
        self.live_axes = {}
        grid = ttk.Frame(parent, padding=8)
        grid.pack(fill="x")
        for i, (_, nm) in enumerate(WINMM_AXES):
            ttk.Label(grid, text="Axis " + nm, width=9).grid(row=i, column=0, sticky="w")
            pb = ttk.Progressbar(grid, maximum=65535, length=420)
            pb.grid(row=i, column=1, padx=6, pady=2)
            lb = ttk.Label(grid, text="0", width=7)
            lb.grid(row=i, column=2)
            self.live_axes[nm] = (pb, lb)
        self.live_pov = ttk.Label(grid, text="POV 0: centred")
        self.live_pov.grid(row=6, column=0, columnspan=3, sticky="w", pady=(6, 0))
        bf = ttk.LabelFrame(parent, text="Buttons (numbered as Vesim expects: Button 0 .. 31)", padding=8)
        bf.pack(fill="x", padx=8, pady=6)
        self.live_btns = []
        for i in range(32):
            l = tk.Label(bf, text=str(i), width=4, relief="groove", bg="#eee")
            l.grid(row=i // 16, column=i % 16, padx=1, pady=1)
            self.live_btns.append(l)
        self.live_note = ttk.Label(parent, foreground="#555", wraplength=900, justify="left",
                                   text="Note: axes are read via the legacy Windows API. X/Y/Z are reliable; "
                                        "the rotary axes may be labelled RX/RY/RZ differently by DirectInput "
                                        "(the game). If an axis behaves oddly in-game, try the neighbouring one.")
        self.live_note.pack(fill="x", padx=10)
        self.tick_live()

    # ---- data / state -----------------------------------------------------
    def vesim_dir(self):
        return os.path.join(self.orbiter, VESIM_REL)

    def is_keyboard(self):
        return self.device.get() == KEYBOARD

    def set_orbiter(self, path, initial=False):
        self.orbiter = path
        if path and os.path.isdir(os.path.join(path, PA_REL)):
            os.makedirs(self.vesim_dir(), exist_ok=True)
            self.root_lbl.config(text="Orbiter / NASSP folder:  " + path)
            self.vesim_on.set(read_flag(path))
            made = self.ensure_files()
            self.refresh_devices(load=True)
            if made:
                self.status.set("Created %d missing file(s) so the game doesn't skip your controllers: %s"
                                % (len(made), ", ".join(made)))
        else:
            self.root_lbl.config(text="No NASSP folder selected - use 'Change Orbiter folder...'")
            self.rows = []
            self.fill_tree()
            if initial:
                self.win.after(200, self.pick_root)

    def pick_root(self):
        d = filedialog.askdirectory(title="Select your Orbiter / NASSP folder (contains Config\\ProjectApollo)",
                                    initialdir=self.orbiter or os.path.expanduser("~"))
        if d:
            if not os.path.isdir(os.path.join(d, PA_REL)):
                messagebox.showerror(APP_TITLE, "That folder has no Config\\ProjectApollo directory.")
                return
            self.set_orbiter(os.path.normpath(d))

    def open_folder(self):
        if self.orbiter and os.path.isdir(self.vesim_dir()):
            os.startfile(self.vesim_dir())

    def refresh_devices(self, load=False):
        names = [KEYBOARD, GENERIC]
        live = self.joys.list()
        for _, nm in live:
            if nm not in names:
                names.append(nm)
        if self.orbiter:
            for nm in sorted(known_devices(self.vesim_dir(), self.vessel.get())):
                if nm not in names:
                    names.append(nm)
        self.dev_cb["values"] = names
        self.live_list = live
        self.live_cb["values"] = ["%d: %s" % (i, nm) for i, nm in live] or ["(no controller detected)"]
        if not self.live_var.get() or self.live_var.get() not in self.live_cb["values"]:
            self.live_cb.current(0)
        # prefer a real stick over the generic placeholder on first load
        if load and self.device.get() == GENERIC and live:
            self.device.set(live[0][1])
        if load:
            self.load_current()

    def on_target_change(self):
        if self.dirty and not self.confirm_discard():
            return
        self.refresh_devices()
        self.load_current()

    def confirm_discard(self):
        ans = messagebox.askyesnocancel(APP_TITLE, "You have unsaved changes. Save them first?")
        if ans is None:
            return False
        if ans:
            return self.save()
        return True

    def template_names(self):
        """Every input this vessel exposes (order + type), from the built-in catalog."""
        return list(CATALOG.get(self.vessel.get(), []))

    def load_current(self, defaults_only=False):
        if not self.orbiter:
            return
        v, d = self.vessel.get(), self.device.get()
        if defaults_only:
            path, rows = None, default_rows(v, d)
        else:
            path, rows = load_chain(self.vesim_dir(), v, d)
            if not path:
                rows = default_rows(v, d)
        self.loaded_from = path
        binds = {}
        types = {}
        for n, t, b in rows:
            binds.setdefault(n, []).append(b)
            types[n] = t or types.get(n, "")
        flat = []
        seen = set()
        for n, t in self.template_names() + [(n, types[n]) for n in types]:
            if n in seen:
                continue
            seen.add(n)
            for b in binds.get(n, [Binding()]):
                flat.append([n, types.get(n) or t, b])
        self.rows = flat
        self.dirty = False
        self.fill_tree()
        target = cfg_path(self.vesim_dir(), v, d, True)
        if path:
            src = os.path.basename(path)
            self.status.set("Loaded %s  ->  will save to %s" % (src, os.path.basename(target)))
        else:
            self.status.set("No saved config for this device - starting blank (nothing mapped). Save creates %s" %
                            os.path.basename(target))
        self.on_select()

    # ---- tree -------------------------------------------------------------
    def row_problem(self, idx):
        name, typ, b = self.rows[idx]
        if not b.mapped():
            return None
        parsed = parse_subdev(b.subdev, self.is_keyboard())
        if parsed is None:
            return "bad"
        if not self.is_keyboard():
            rot, trn = AXIS_GROUPS.get(self.vessel.get(), ((), ()))
            if name in rot or name in trn:
                other = trn if name in rot else rot
                for j, (n2, _, o) in enumerate(self.rows):
                    if j != idx and n2 in other and o.mapped() and parse_subdev(o.subdev, False) == parsed:
                        return "warn"
        if self.is_keyboard():
            k = KEYS_LOWER.get(b.subdev.strip().lower())
            for j, (_, _, o) in enumerate(self.rows):
                if j != idx and o.mapped() and KEYS_LOWER.get(o.subdev.strip().lower()) == k:
                    return "warn"
        return None

    def fill_tree(self):
        sel = self.selected_index()
        self.tv.delete(*self.tv.get_children())
        self.iid_row = {}
        q = self.flt.get().strip().lower()
        for i, (n, t, b) in enumerate(self.rows):
            if q and q not in n.lower() and q not in b.subdev.lower():
                continue
            if self.only_mapped.get() and not b.mapped():
                continue
            iid = str(i)
            self.iid_row[iid] = i
            self.tv.insert("", "end", iid=iid, values=self.row_values(i), tags=self.row_tags(i))
        if sel is not None and str(sel) in self.iid_row:
            self.tv.selection_set(str(sel))

    def row_values(self, i):
        n, t, b = self.rows[i]
        return (n, t, b.subdev.strip() if b.mapped() else "-", "yes" if b.reverse and b.mapped() else "")

    def row_tags(self, i):
        b = self.rows[i][2]
        if not b.mapped():
            return ("unmapped",)
        p = self.row_problem(i)
        return (p,) if p else ()

    def refresh_row(self, i):
        if str(i) in self.iid_row:
            self.tv.item(str(i), values=self.row_values(i), tags=self.row_tags(i))
        for iid, j in self.iid_row.items():  # duplicate / overlap warnings can change other rows
            self.tv.item(iid, tags=self.row_tags(j))

    def selected_index(self):
        s = self.tv.selection() if hasattr(self, "tv") else ()
        return self.iid_row.get(s[0]) if s else None

    # ---- editor -----------------------------------------------------------
    def set_editor_enabled(self, on):
        st = "readonly" if on else "disabled"
        self.kind_cb.config(state=st)
        self.value_cb.config(state=st)
        for wdg in (self.rev_chk, self.listen_btn, self.add_btn, self.clear_btn):
            wdg.config(state="normal" if on else "disabled")

    def kinds(self):
        return ["Key"] if self.is_keyboard() else JOY_KINDS

    def values_for(self, kind):
        return KEYS if kind == "Key" else JOY_VALUES.get(kind, [])

    def on_select(self, _e=None):
        i = self.selected_index()
        if i is None:
            self.sel_lbl.config(text="(select a row)")
            self.hint.set("")
            self.set_editor_enabled(False)
            return
        name, typ, b = self.rows[i]
        self.editing = True
        self.set_editor_enabled(True)
        self.sel_lbl.config(text="%s  [%s]" % (name, typ or "?"))
        self.kind_cb["values"] = self.kinds()
        parsed = parse_subdev(b.subdev, self.is_keyboard()) if b.mapped() else None
        if parsed:
            self.kind.set(parsed[0])
            self.value_cb["values"] = self.values_for(parsed[0])
            self.value.set(parsed[1])
        else:
            self.kind.set(self.kinds()[0] if not b.mapped() else "")
            self.value_cb["values"] = self.values_for(self.kind.get())
            self.value.set("")
        self.reverse.set(b.reverse)
        self.editing = False
        t = (typ or "").lower()
        if t == "axis":
            self.hint.set("Axis input. Bound to a joystick button, 'Reverse' makes it the minimum "
                          "value instead of the maximum - bind two buttons (one reversed) for +/-.")
        else:
            self.hint.set("Button input. Bound to an axis, it triggers when the axis is pushed to "
                          "its extreme (Reverse flips the direction).")
        rot, trn = AXIS_GROUPS.get(self.vessel.get(), ((), ()))
        tip = None
        if name == TOGGLE or name in rot:
            tip = TIP_SINGLE % (" / ".join(rot), " / ".join(trn))
        elif name in trn:
            tip = ("Only needed if translation has its OWN control. On the same axis as %s both "
                   "rotate and translate in rotation mode (shown in orange). For one stick, leave "
                   "this empty and use the Rotation/Translation toggle." % " / ".join(rot))
        if tip:
            self.hint.set(self.hint.get() + "\n\nTIP: " + tip)

    def on_kind(self, _e=None):
        if self.editing:
            return
        vals = self.values_for(self.kind.get())
        self.value_cb["values"] = vals
        self.value.set(vals[0] if vals else "")
        self.on_value()

    def on_value(self, _e=None):
        if self.editing:
            return
        i = self.selected_index()
        if i is None:
            return
        b = self.rows[i][2]
        b.subdev = compose_subdev(self.kind.get(), self.value.get()) if self.value.get() else ""
        b.reverse = bool(self.reverse.get())
        self.set_dirty()
        self.refresh_row(i)

    def add_binding(self):
        i = self.selected_index()
        if i is None:
            return
        name, typ, _ = self.rows[i]
        self.rows.insert(i + 1, [name, typ, Binding()])
        self.set_dirty()
        self.fill_tree()
        self.tv.selection_set(str(i + 1))
        self.tv.see(str(i + 1))

    def clear_binding(self):
        i = self.selected_index()
        if i is None:
            return
        name, typ, b = self.rows[i]
        same = [j for j, r in enumerate(self.rows) if r[0] == name]
        if len(same) > 1:
            del self.rows[i]
        else:
            b.subdev, b.reverse, b.modifier = "", False, ""
        self.set_dirty()
        self.fill_tree()
        self.on_select()

    def set_dirty(self, d=True):
        self.dirty = d
        self.win.title(APP_TITLE + (" *" if d else ""))

    # ---- listen -----------------------------------------------------------
    def current_live_ids(self):
        """winmm ids to watch: the selected device if connected, else all."""
        dev = self.device.get()
        ids = [i for i, nm in self.live_list if nm == dev]
        return ids or [i for i, _ in self.live_list]

    def start_listen(self):
        if self.selected_index() is None or self.listening:
            return
        kb = self.is_keyboard()
        self.listening = {"t0": time.time(), "base": {}, "kb": kb}
        if not kb:
            self.live_list = self.joys.list()
            for jid in self.current_live_ids():
                self.listening["base"][jid] = self.joys.read(jid)
            if not self.listening["base"]:
                self.listening = None
                messagebox.showinfo(APP_TITLE, "No connected game controller was detected.\n"
                                    "Pick the control manually from the dropdowns instead.")
                return
        self.listen_btn.config(text="Listening... (Esc to cancel)")
        self.win.bind_all("<KeyPress>", self.on_listen_key)
        self.poll_listen()

    def stop_listen(self):
        self.listening = None
        self.listen_btn.config(text="Listen... (move / press)")
        self.win.unbind_all("<KeyPress>")

    def on_listen_key(self, e):
        if not self.listening:
            return
        if not self.listening["kb"]:
            if e.keysym == "Escape":
                self.stop_listen()
            return "break"
        name = keysym_to_name(e.keysym)
        if name:
            self.stop_listen()
            self.apply_detected("Key", name)
        return "break"

    def poll_listen(self):
        L = self.listening
        if not L:
            return
        if time.time() - L["t0"] > 10:
            self.stop_listen()
            return
        if not L["kb"]:
            for jid, base in L["base"].items():
                cur = self.joys.read(jid)
                if not cur or not base:
                    continue
                for nm, v in cur["axes"].items():
                    if abs(v - base["axes"][nm]) > 20000:
                        self.stop_listen()
                        self.apply_detected("Axis", nm)
                        return
                newbtn = cur["buttons"] & ~base["buttons"]
                if newbtn:
                    n = (newbtn & -newbtn).bit_length() - 1
                    self.stop_listen()
                    self.apply_detected("Button", str(n))
                    return
                if cur["pov"] != 0xFFFF and base["pov"] == 0xFFFF:
                    horiz = cur["pov"] in (9000, 27000)
                    self.stop_listen()
                    self.apply_detected("POV", "0H" if horiz else "0V")
                    return
        self.win.after(30, self.poll_listen)

    def apply_detected(self, kind, value):
        self.editing = True
        self.kind.set(kind)
        self.value_cb["values"] = self.values_for(kind)
        self.value.set(value)
        self.editing = False
        self.on_value()

    # ---- live monitor -----------------------------------------------------
    def tick_live(self):
        try:
            if self.nb.index(self.nb.select()) == 1:
                sel = self.live_cb.current()
                data = None
                if 0 <= sel < len(getattr(self, "live_list", [])):
                    data = self.joys.read(self.live_list[sel][0])
                for nm, (pb, lb) in self.live_axes.items():
                    v = data["axes"][nm] if data else 0
                    pb["value"] = v
                    lb.config(text=str(v))
                for i, l in enumerate(self.live_btns):
                    on = bool(data and data["buttons"] >> i & 1)
                    l.config(bg="#4caf50" if on else "#eee")
                if data and data["pov"] != 0xFFFF:
                    self.live_pov.config(text="POV 0: %.0f deg" % (data["pov"] / 100.0))
                else:
                    self.live_pov.config(text="POV 0: centred")
        finally:
            self.win.after(50, self.tick_live)

    # ---- actions ----------------------------------------------------------
    def problems(self):
        return [self.rows[i][0] + " -> " + self.rows[i][2].subdev
                for i in range(len(self.rows)) if self.row_problem(i) == "bad"]

    def save(self):
        if not self.orbiter:
            return False
        bad = self.problems()
        if bad and not messagebox.askyesno(
                APP_TITLE, "These bindings are not valid names and Vesim will ignore them:\n\n  "
                + "\n  ".join(bad[:10]) + "\n\nSave anyway?"):
            return False
        path = cfg_path(self.vesim_dir(), self.vessel.get(), self.device.get(), True)
        try:
            write_cfg(path, [tuple(r) for r in self.rows])
        except OSError as ex:
            messagebox.showerror(APP_TITLE, "Could not save:\n%s" % ex)
            return False
        self.set_dirty(False)
        self.loaded_from = path
        self.refresh_devices()
        self.status.set("Saved %s  (%d mapped)" % (os.path.basename(path),
                                                   sum(1 for r in self.rows if r[2].mapped())))
        return True

    def vesim_files(self):
        try:
            return sorted(f for f in os.listdir(self.vesim_dir())
                          if os.path.isfile(os.path.join(self.vesim_dir(), f)))
        except OSError:
            return []

    def ensure_files(self):
        """Create a blank .launchpad.cfg only where the game would otherwise find nothing: Vesim
        stops setting up devices at the first one with no config in its fallback chain, and the
        keyboard is always first. Covers Keyboard plus every attached stick, for CSM and LM."""
        if not self.orbiter:
            return []
        made = []
        for v in VESSELS:
            for d in [KEYBOARD] + [nm for _, nm in self.joys.list()]:
                if load_chain(self.vesim_dir(), v, d)[0] is None:
                    p = cfg_path(self.vesim_dir(), v, d, True)
                    write_cfg(p, default_rows(v, d))
                    made.append(os.path.basename(p))
        return made

    def rescan(self):
        made = self.ensure_files()
        self.refresh_devices()
        if made:
            self.status.set("Created %d missing file(s): %s" % (len(made), ", ".join(made)))

    def create_all_devices(self, quiet=False):
        """Write a .launchpad.cfg (every input listed, nothing mapped) for Keyboard, GenericJoystick and
        every attached stick, for both vessels. Existing files are never overwritten."""
        if not self.orbiter:
            return
        devices = [KEYBOARD, GENERIC] + [nm for _, nm in self.joys.list()]
        made = []
        for v in VESSELS:
            for d in devices:
                p = cfg_path(self.vesim_dir(), v, d, True)
                if not os.path.exists(p):
                    write_cfg(p, default_rows(v, d))
                    made.append(os.path.basename(p))
        self.refresh_devices()
        self.load_current()
        self.status.set("Created %d file(s), %d already existed." % (len(made), len(devices) * len(VESSELS) - len(made)))
        if not quiet:
            messagebox.showinfo(APP_TITLE, "Created %d file(s):\n\n%s" % (len(made), "\n".join(made) or "(none - all already exist)"))

    def clear_all_files(self):
        files = self.vesim_files()
        if not self.orbiter:
            return
        if not files:
            messagebox.showinfo(APP_TITLE, "The Vesim folder is already empty.")
            return
        stamp = time.strftime("%Y%m%d_%H%M%S")
        dest = os.path.join(self.orbiter, PA_REL, "Vesim_backup_" + stamp)
        if not messagebox.askyesno(
                APP_TITLE,
                "This moves ALL %d files out of the Vesim folder (shipped defaults, your "
                ".launchpad.cfg files and backups) into:\n\n%s\n\nNothing is deleted - you can move them back.\n\n"
                "Until every device has a file again the game may skip your controllers, so you'll "
                "be offered to create fresh files for every detected device right after.\n\nContinue?"
                % (len(files), dest), icon="warning"):
            return
        try:
            os.makedirs(dest)
            for f in files:
                shutil.move(os.path.join(self.vesim_dir(), f), os.path.join(dest, f))
        except OSError as ex:
            messagebox.showerror(APP_TITLE, "Could not move files:\n%s" % ex)
            return
        self.set_dirty(False)
        self.refresh_devices()
        self.load_current()
        self.status.set("Moved %d files to %s" % (len(files), dest))
        if messagebox.askyesno(APP_TITLE, "Create fresh files now for Keyboard, GenericJoystick and %d detected "
                               "controller(s), for CSM and LM?" % len(self.joys.list())):
            self.create_all_devices(quiet=True)
            self.status.set("Moved %d files to a backup folder and created fresh files for all devices." % len(files))

    def reset_defaults(self):
        if messagebox.askyesno(APP_TITLE, "Remove every binding for this device (all inputs unmapped)?"):
            self.load_current(defaults_only=True)
            self.set_dirty(True)

    def copy_from(self):
        """Copy mappings from another device's config (e.g. Keyboard layout, other stick)."""
        names = sorted(known_devices(self.vesim_dir(), self.vessel.get()) - {self.device.get()})
        if not names:
            messagebox.showinfo(APP_TITLE, "No other device configs exist for this vessel.")
            return
        dlg = tk.Toplevel(self.win)
        dlg.title("Copy mappings from...")
        dlg.transient(self.win)
        dlg.grab_set()
        var = tk.StringVar(value=names[0])
        ttk.Label(dlg, text="Copy all mappings from:").pack(padx=14, pady=(14, 4))
        ttk.Combobox(dlg, textvariable=var, values=names, state="readonly", width=44).pack(padx=14)

        def go():
            _, rows = load_chain(self.vesim_dir(), self.vessel.get(), var.get())
            dlg.destroy()
            binds = {}
            for n, _t, b in rows:
                binds.setdefault(n, []).append(b)
            flat = []
            seen = set()
            for n, t, _b in self.rows:
                if n in seen:
                    continue
                seen.add(n)
                for b in binds.get(n, [Binding()]):
                    flat.append([n, t, Binding(b.subdev, b.reverse, b.modifier)])
            self.rows = flat
            self.set_dirty()
            self.fill_tree()
            self.on_select()
        ttk.Button(dlg, text="Copy", command=go).pack(pady=12)

    def on_flag(self):
        if not self.orbiter:
            return
        try:
            write_flag(self.orbiter, self.vesim_on.get())
        except OSError as ex:
            messagebox.showerror(APP_TITLE, "Could not update %s:\n%s" % (FLAG_REL, ex))
            return
        self.status.set("JOYSTICK_VESIM %d written to %s  (this disables the legacy RHC/THC joystick options)" %
                        (1 if self.vesim_on.get() else 0, FLAG_REL))

    def on_close(self):
        if self.dirty and not self.confirm_discard():
            return
        self.win.destroy()


def main():
    root = find_orbiter_root()
    for a in sys.argv[1:]:
        if os.path.isdir(a):
            root = os.path.abspath(a)
    win = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    app = App(win, root)
    if "--selftest" in sys.argv:
        win.update()
        print("rows:", len(app.rows), "device:", app.device.get(), "loaded:", app.loaded_from)
        win.destroy()
        return
    win.mainloop()


if __name__ == "__main__":
    main()
