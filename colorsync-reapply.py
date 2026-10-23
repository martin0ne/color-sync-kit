#!/usr/bin/env python3
"""colorsync-reapply — ponawia aktywne korekty gamma z state.json.

Launchd odpala to co 5 min: gdy system wyzeruje gamma tables
(uśpienie ekranu, przełączenie trybów), korekty wracają same.
Cisza przy braku pliku stanu; nieistniejący ekran (dock śpi) da wpis
`rc=2 BŁĄD...` w logu i ponowi próbę w kolejnym cyklu — to nie awaria.
"""
import json
import os
import subprocess
import sys

STATE = os.path.expanduser("~/.config/colorsync/state.json")
COLORSYNC = os.path.expanduser("~/bin/colorsync.py")
LOG = os.path.expanduser("~/.config/colorsync/reapply.log")

if not os.path.exists(STATE):
    sys.exit(0)

try:
    with open(STATE) as f:
        st = json.load(f)
except (json.JSONDecodeError, OSError):
    # uszkodzony stan — nie awaryjuj w pętli, poczekaj na kolejny cykl
    sys.exit(0)

lines = []
for key, v in st.get("applied", {}).items():
    rgb = v.get("rgb")
    if not rgb:
        continue
    try:
        p = subprocess.run(
            [sys.executable, COLORSYNC, "apply", key,
             "--rgb", *[str(x) for x in rgb]],
            capture_output=True, text=True, timeout=30,
        )
        lines.append(f"{key}: rc={p.returncode} {p.stdout.strip() or p.stderr.strip()}")
    except subprocess.TimeoutExpired:
        lines.append(f"{key}: TIMEOUT 30s")

if lines:
    from datetime import datetime
    with open(LOG, "a") as f:
        f.write(f"{datetime.now().isoformat(timespec='seconds')} | " + " ; ".join(lines) + "\n")
    # tniemy log do ostatnich 200 linii
    with open(LOG) as f:
        tail = f.readlines()[-200:]
    with open(LOG, "w") as f:
        f.writelines(tail)
