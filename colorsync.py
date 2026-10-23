#!/usr/bin/env python3
"""colorsync — dopasowanie kolorów/jasności ekranów przez gamma tables macOS.

PO CO:   Kolor-sync 2 identycznych monitorów (Dell U2415 przez Dell TB dock)
         bez DDC/CI (dock blokuje DDC) i bez kalibratora sprzętowego.
         Mechanizm: software'owa korekta punktu bieli per ekran przez
         CGSetDisplayTransferByTable (to samo, co robi f.lux).
JAK:     1) `measure` — policz p50 RGB łatki tła z każdego ekranu na JEDNYM
            zdjęciu (boxes w ułamkach W,H; łatka = jednolite tło pulpitu).
         2) `apply` — pomnóż gamma table ekranu przez współczynniki tak, by
            punkt bieli zrównał się z ekranem wzorcowym.
         3) `snapshot` PRZED pierwszym apply (backup), `reset` cofa.
CO ZWRACA: exit 0 = wykonane (melduje co zmienił); exit 2 = pusto/nie znalazł;
         exit 1 = błąd. Każda zmiana ląduje w state.json z timestampem.

Przykłady:
  python3 ~/bin/colorsync.py list
  python3 ~/bin/colorsync.py snapshot
  python3 ~/bin/colorsync.py measure /sciezka/zdjecie.jpg \\
      --boxes "lewy:0.08,0.05,0.40,0.95;prawy:0.52,0.05,0.85,0.95" --ref lewy
  python3 ~/bin/colorsync.py apply 3 --rgb 0.97,1.0,0.99
  python3 ~/bin/colorsync.py apply 3 --dry-run --rgb 0.97,1.0,0.99
  python3 ~/bin/colorsync.py reset 3
  python3 ~/bin/colorsync.py status
"""
import argparse, ctypes, datetime, json, os, sys

STATE_DIR = os.path.expanduser("~/.config/colorsync")
STATE_PATH = os.path.join(STATE_DIR, "state.json")


def now(): return datetime.datetime.now().isoformat(timespec="seconds")


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {"snapshots": {}, "applied": {}}


def save_state(st):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(st, f, indent=1, ensure_ascii=False)
    os.chmod(STATE_PATH, 0o600)


def die(msg, code=1):
    print(f"BŁĄD: {msg}", file=sys.stderr); sys.exit(code)


# ---------- Quartz (pyobjc-framework-Quartz) ----------
def _quartz():
    try:
        import Quartz
        return Quartz
    except ImportError:
        die("brak pyobjc-framework-Quartz: pip3 install pyobjc-framework-Quartz")


def displays():
    Q = _quartz()
    err, ids, n = Q.CGGetOnlineDisplayList(8, None, None)
    if err != 0:
        die(f"CGGetOnlineDisplayList err={err}")
    out = []
    for did in ids[:n]:
        out.append({
            "id": did,
            "builtin": bool(Q.CGDisplayIsBuiltin(did)),
            "active": bool(Q.CGDisplayIsActive(did)),
            "w": Q.CGDisplayPixelsWide(did),
            "h": Q.CGDisplayPixelsHigh(did),
        })
    return out


def get_tables(did):
    Q = _quartz()
    n = Q.CGDisplayGammaTableCapacity(did)
    if n <= 0:
        die(f"display {did}: gamma capacity={n} (brak dostępu?)")
    A = ctypes.c_float * n
    r, g, b = A(), A(), A()
    res = Q.CGGetDisplayTransferByTable(did, n, r, g, b, None)
    # pyobjc zwraca (status, r, g, b, sampleCount)
    status = res[0] if isinstance(res, tuple) else res
    if status != 0:
        die(f"display {did}: CGGetDisplayTransferByTable status={status}")
    return list(r), list(g), list(b)


def set_tables(did, r, g, b):
    Q = _quartz()
    n = len(r)
    A = ctypes.c_float * n
    res = Q.CGSetDisplayTransferByTable(did, n, A(*r), A(*g), A(*b))
    status = res[0] if isinstance(res, tuple) else res
    if status != 0:
        die(f"display {did}: CGSetDisplayTransferByTable status={status}")
    return True


# ---------- komendy ----------
def cmd_list(_):
    ds = displays()
    if not ds:
        print("BRAK: nie znaleziono żadnych ekranów"); return 2
    for d in ds:
        tag = "builtin" if d["builtin"] else "zewn."
        print(f"id={d['id']}  {tag:6s} {'aktywny' if d['active'] else 'offline'}  {d['w']}x{d['h']}")
    print("(id z tej listy używaj w apply/reset/snapshot; nazwę panelu zweryfikuj wzrokiem)")
    return 0


def cmd_snapshot(args):
    st = load_state()
    for d in displays():
        r, g, b = get_tables(d["id"])
        st["snapshots"][str(d["id"])] = {"r": r, "g": g, "b": b, "saved": now()}
    save_state(st)
    print(f"OK: snapshot gamma zapisany dla {len(st['snapshots'])} ekranów -> {STATE_PATH}")
    return 0


def cmd_apply(args):
    st = load_state()
    key = str(args.display)
    ids = {str(d["id"]) for d in displays()}
    if key not in ids:
        die(f"display {args.display} nie istnieje. Uruchom `list` po id.", 2)
    if key not in st["snapshots"]:
        # D2: backup przed modyfikacją — automatyczny
        r, g, b = get_tables(args.display)
        st["snapshots"][key] = {"r": r, "g": g, "b": b, "saved": now()}
        print(f"(auto-snapshot gamma display {args.display} przed zmianą)")

    snap = st["snapshots"][key]
    def mult(table, factor):
        return [min(1.0, max(0.0, v * factor)) for v in table]

    new = [mult(snap["r"], args.rgb[0]), mult(snap["g"], args.rgb[1]), mult(snap["b"], args.rgb[2])]

    if args.dry_run:
        mid = len(new[0]) // 2
        print(f"DRY-RUN: display {args.display} RGB gain {args.rgb} -> "
              f"mid R {snap['r'][mid]:.4f}->{new[0][mid]:.4f}, "
              f"G {snap['g'][mid]:.4f}->{new[1][mid]:.4f}, "
              f"B {snap['b'][mid]:.4f}->{new[2][mid]:.4f}; nic nie zapisano")
        return 0

    set_tables(args.display, *new)
    # weryfikacja zapisu (nie ufamy err==0)
    chk = get_tables(args.display)
    mid = len(chk[0]) // 2
    ok = abs(chk[0][mid] - new[0][mid]) < 0.005
    st["applied"][key] = {"rgb": args.rgb, "at": now(), "verified": ok}
    save_state(st)
    print(f"{'OK' if ok else 'NIEPOTWIERDZONE'}: display {args.display} rgb={args.rgb} "
          f"(mid R {chk[0][mid]:.4f} G {chk[1][mid]:.4f} B {chk[2][mid]:.4f}) at {st['applied'][key]['at']}")
    return 0 if ok else 1


def cmd_reset(args):
    st = load_state()
    targets = ([d["id"] for d in displays()] if args.target == "all"
               else [int(args.target)])
    for did in targets:
        snap = st["snapshots"].get(str(did))
        if snap:
            set_tables(did, snap["r"], snap["g"], snap["b"])
            st["applied"].pop(str(did), None)
            print(f"OK: display {did} przywrócony ze snapshotu ({snap['saved']})")
        else:
            # brak snapshotu -> identyczność liniowa
            n = ctypes.c_float
            r, g, b = get_tables(did)
            nch = len(r)
            lin = [i / (nch - 1) for i in range(nch)]
            set_tables(did, lin, lin, lin)
            st["applied"].pop(str(did), None)
            print(f"OK: display {did} ustawiony na liniową (brak snapshotu)")
    save_state(st)
    return 0


def cmd_status(_):
    st = load_state()
    if not st["applied"]:
        print("PUSTO: brak aktywnych korekt (uruchom `apply`, aby je nałożyć)")
        return 2
    for k, v in st["applied"].items():
        print(f"display {k}: rgb={v['rgb']} at={v['at']} verified={v['verified']}")
    return 0


def cmd_measure(args):
    try:
        from PIL import Image
    except ImportError:
        die("brak Pillow: pip3 install pillow")
    if not os.path.exists(args.photo):
        die(f"plik nie istnieje: {args.photo}", 2)
    im = Image.open(args.photo).convert("RGB")
    W, H = im.size
    results = {}
    for spec in args.boxes.split(";"):
        name, box = spec.split(":")
        x1, y1, x2, y2 = (float(v) for v in box.split(","))
        c = im.crop((int(x1 * W), int(y1 * H), int(x2 * W), int(y2 * H)))
        # subsampling dla szybkości; p50 odporne na mory/OSD/refleksy punktowe
        px = c.load()
        cw, ch = c.size
        step = max(1, (cw * ch) // 60000)
        vals = ([], [], [])
        i = 0
        for yy in range(0, ch, max(1, int(step ** 0.5))):
            for xx in range(0, cw, max(1, int(step ** 0.5))):
                p = px[xx, yy]
                vals[0].append(p[0]); vals[1].append(p[1]); vals[2].append(p[2])
        p50 = tuple(sorted(v)[len(v) // 2] for v in vals)
        results[name] = p50
    if args.ref and args.ref in results and len(results) > 1:
        ref = results[args.ref]
        print(f"ref={args.ref} p50 RGB={ref}")
        for name, p50 in results.items():
            if name == args.ref:
                continue
            dl = (sum(p50) / 3) / (sum(ref) / 3)
            db = (p50[2] / max(1, p50[0])) / (ref[2] / max(1, ref[0]))
            print(f"{name}: p50 RGB={p50}  jasność vs ref: {dl:.3f}  "
                  f"(1.0=identyczna; <1 -> ciemniejszy)  ciepło vs ref: {db:.3f} "
                  f"(1.0=identyczne; <1 -> cieplejszy, podnieś B)")
    else:
        for name, p50 in results.items():
            print(f"{name}: p50 RGB={p50}")
    st = load_state()
    st["last_measure"] = {"photo": args.photo, "at": now(), "results": results, "ref": args.ref or ""}
    save_state(st)
    print(f"(zapisane w {STATE_PATH} jako last_measure @{now()})")
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="lista ekranów z id do używania w apply/reset").set_defaults(fn=cmd_list)
    s = sub.add_parser("snapshot", help="backup obecnych gamma tables (rób PRZED apply)")
    s.set_defaults(fn=cmd_snapshot)
    s = sub.add_parser("apply", help="nałóż korektę RGB (mnożniki ~0.95-1.05)")
    s.add_argument("display", type=int, help="id ekranu z `list`")
    s.add_argument("--rgb", type=float, nargs=3, metavar=("R", "G", "B"), required=True,
                   help="mnożniki gain, np. 0.97 1.0 0.99")
    s.add_argument("--dry-run", action="store_true", help="pokaż co zrobi, nic nie zapisuj")
    s.set_defaults(fn=cmd_apply)
    s = sub.add_parser("reset", help="cofnij do snapshotu (lub `all`)")
    s.add_argument("target", help="id ekranu albo 'all'")
    s.set_defaults(fn=cmd_reset)
    sub.add_parser("status", help="aktywne korekty + timestampy").set_defaults(fn=cmd_status)
    s = sub.add_parser("measure", help="p50 RGB łatek ze zdjęcia (ułamki W,H)")
    s.add_argument("photo")
    s.add_argument("--boxes", required=True, help='"nazwa:x1,y1,x2,y2;nazwa:..."')
    s.add_argument("--ref", default="", help="nazwa ekranu wzorcowego")
    s.set_defaults(fn=cmd_measure)
    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
