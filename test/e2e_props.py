"""E2E: the Project Props pak loads in the real game and every placement becomes a world entity.

Needs bin/ProjectPropsDE_P.pak copied into Gameface/Content/Paks/~mods (the folder is admin-only) and a save that
loads into gameplay by itself; installs IplActorsDE/bin/IplActorsDE.asi next to the exe. Launches DE, walks
the building and dummy pools (CFileLoader::LoadObjectInstance takes a CBuilding, or a CDummy for object.dat models),
matches every pak placement by model id and position and checks the ASI cleared the IPL actor-link flag
(entity +0x34 bit 3, see ../README.md) on exactly those. Then moves the player next to the nearest pak dumpster and
counts placements within 60 m that got a UE actor (entity +0x20).
Screens: %TEMP%/e2e_props.png (4 s after the move), e2e_props_late.png (24 s). Writes test/e2e_props.txt.
The pool/camera/player addresses below are for SanAndreas.exe ed7545eb… only (the ASIs themselves use signatures).
Usage: py -3.12 test/e2e_props.py   (game must be closed; ~2 minutes; do not touch mouse/keyboard)"""
import ctypes, filecmp, math, os, shutil, struct, subprocess, sys, tempfile, time
from collections import Counter
from PIL import ImageGrab

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from game import GAME, focus, k32, module_base, pid_of, read  # noqa: E402

PAK = os.path.join(HERE, "..", "bin", "ProjectPropsDE_P.pak")
MODS = os.path.join(GAME, "..", "..", "Content", "Paks", "~mods", "ProjectPropsDE_P.pak")
ASI = os.path.join(HERE, "..", "IplActorsDE", "bin", "IplActorsDE.asi")
DATA = os.path.join(HERE, "..", "obj", "{}", "Gameface", "Content", "OriginalData", "GTASA", "data")  # build.py staging
POOLS = {"buildings": (0x572A588, 112), "dummies": (0x572A578, 120)}  # CPools: objects*, flags*, int size; flag bit 7 = free
CAM_MATRIX = 0x53E13F8  # TheCamera.m_matrix (CMatrix*)
PLAYERS = 0x53EA730  # CWorld::Players[0].m_pPed; ped +0x634 bit 0x100 = in a vehicle, +0x7C8 = that vehicle
OUT = os.path.join(HERE, "e2e_props.txt")
CRASHES = os.path.expanduser(r"~\Documents\Rockstar Games\GTA San Andreas Definitive Edition\Crashes")


def q(h, a): return struct.unpack("<Q", read(h, a, 8))[0]


def key(model, x, y, z): return model, round(x, 2), round(y, 2), round(z, 2)


def f32(s): return struct.unpack("<f", struct.pack("<f", float(s)))[0]  # the game keeps positions as float


def entities(h, base, rva, stride):
    """(address, (model, x, y, z)) of every used slot; CEntity: +0x08 inline pos, +0x18 CMatrix* (pos at +0x30), +0x3A model."""
    p = q(h, base + rva)
    objs, flags, size = q(h, p), q(h, p + 8), struct.unpack("<i", read(h, p + 16, 4))[0]
    raw, fl = read(h, objs, size * stride), read(h, flags, size)
    for i in range(size):
        if fl[i] >= 0x80:
            continue
        e = raw[i * stride:(i + 1) * stride]
        m = struct.unpack_from("<Q", e, 0x18)[0]
        pos = struct.unpack("<3f", read(h, m + 0x30, 12)) if m else struct.unpack_from("<3f", e, 0x08)
        yield objs + i * stride, key(struct.unpack_from("<h", e, 0x3A)[0], *pos)


def placements():
    """The inst lines the pak adds to DE's IPLs (pak copy minus DE's copy, both left in obj/ by build.py)."""
    for d, _, fs in os.walk(DATA.format("pak")):
        for f in fs:
            rel = os.path.relpath(os.path.join(d, f), DATA.format("pak"))
            stock = set(open(os.path.join(DATA.format("stock"), rel), errors="replace").read().splitlines())
            for line in open(os.path.join(d, f), errors="replace").read().splitlines():
                t = [x.strip() for x in line.split(",")]
                if line not in stock and len(t) == 12:
                    yield rel, t[1], key(int(t[0]), f32(t[3]), f32(t[4]), f32(t[5]))


def main():
    if pid_of("SanAndreas.exe"): sys.exit("close the game first")
    if not os.path.exists(MODS) or not filecmp.cmp(PAK, MODS, shallow=False):
        sys.exit(f"copy {os.path.abspath(PAK)} to {os.path.abspath(MODS)} first")
    wanted = list(placements())
    shutil.copy(ASI, GAME)
    started = time.time()
    subprocess.Popen([os.path.join(GAME, "SanAndreas.exe")], cwd=GAME)
    time.sleep(80)
    pid = pid_of("SanAndreas.exe")
    lines, found, actors, flagged = [], Counter(), ([], []), (0, -1)
    try:
        if not pid: raise RuntimeError("game exited during loading")
        h = k32.OpenProcess(0x0438, False, pid)  # QUERY_INFORMATION | VM_READ | VM_WRITE | VM_OPERATION
        base = module_base(pid)
        live, ours = Counter(), {}  # ours: entity address -> key, for the pak's placements
        need = Counter(k for _, _, k in wanted)
        left = Counter(need)  # a stock entity can share a key with a placement only if it sits exactly there
        for name, (rva, stride) in POOLS.items():
            ents = list(entities(h, base, rva, stride))
            live.update(k for _, k in ents)
            for addr, k in ents:
                if left[k] > 0:
                    left[k] -= 1; ours[addr] = k
            lines.append(f"{name}: {len(ents)} used")
        found = {k: min(n, live[k]) for k, n in need.items()}
        per_file = Counter(f for f, _, k in wanted)
        miss = Counter(f for f, _, k in wanted if live[k] < need[k])
        lines += [f"missing in {f}: {miss[f]}/{per_file[f]}" for f in sorted(miss)]
        # IplActorsDE clears +0x34 bit 3 on `-1`-indexed IPL lines; DE sets it on every other IPL instance
        stock_unlinked = sum(1 for n, (rva, stride) in POOLS.items() for a, _ in entities(h, base, rva, stride)
                             if a not in ours and not read(h, a + 0x34, 1)[0] & 0x08)
        ours_unlinked = sum(1 for a in ours if not read(h, a + 0x34, 1)[0] & 0x08)
        lines.append(f"link flag clear: pak placements {ours_unlinked}/{len(ours)}, other entities {stock_unlinked}")
        flagged = (ours_unlinked, len(ours))
        ped = q(h, base + PLAYERS)
        in_car = struct.unpack("<I", read(h, ped + 0x634, 4))[0] & 0x100
        ent = (in_car and q(h, ped + 0x7C8)) or ped  # FindPlayerEntity
        m = q(h, ent + 0x18)
        here = struct.unpack("<3f", read(h, m + 0x30, 12))
        big = [w for w in wanted if "wreck" in w[1].lower() or "dump" in w[1].lower()] or wanted
        f, name, (_, x, y, z) = min(big, key=lambda w: math.dist(w[2][1:3], here[:2]))
        fwd = struct.unpack("<3f", read(h, m + 0x10, 12))  # park 10 m before it, facing it
        k32.WriteProcessMemory(h, ctypes.c_void_p(m + 0x30), struct.pack("<3f", x - 10 * fwd[0], y - 10 * fwd[1], z + 1), 12, None)
        k32.WriteProcessMemory(h, ctypes.c_void_p(ent + 0x7C), b"\0" * 12, 12, None)  # CPhysical::m_vecMoveSpeed
        focus(pid); time.sleep(4)  # before a teleported bike tips over and the camera swings down
        print(f"moved next to {name} ({f}) at {x} {y} {z}")
        cam = q(h, base + CAM_MATRIX)  # CMatrix: right, forward, up, pos rows of 16 bytes
        fwd, pos = struct.unpack("<3f", read(h, cam + 0x10, 12)), struct.unpack("<3f", read(h, cam + 0x30, 12))
        ImageGrab.grab().save(os.path.join(tempfile.gettempdir(), "e2e_props.png"))
        seen = []  # pak placements in front of the camera, to compare against the screenshot by eye
        for f, name, (_, x, y, z) in wanted:
            d = (x - pos[0], y - pos[1], z - pos[2]); n = math.hypot(*d)
            if 0 < n < 80 and sum(a * b for a, b in zip(d, fwd)) / n > 0.8:
                seen.append((round(n), name, f))
        print(f"camera {pos} forward {fwd}; pak placements in view (m, model, IPL): {sorted(seen)}")
        time.sleep(20)  # stay among the props: physics/streaming there is what ran out of matrices before
        near = [a for a, (_, x, y, z) in ours.items() if math.dist((x, y), pos[:2]) < 60]
        linked = [a for a in near if q(h, a + 0x20)]  # CEntity +0x20: the UE actor CreateRwObject returned
        lines.append(f"pak placements within 60 m: {len(near)}, with a UE actor: {len(linked)}")
        ImageGrab.grab().save(os.path.join(tempfile.gettempdir(), "e2e_props_late.png"))
        actors = (near, linked)
    except Exception as e:
        lines.append(f"error: {e}")
    finally:
        subprocess.run(["taskkill", "/IM", "SanAndreas.exe", "/F"], capture_output=True)
    total = len(wanted)
    placed = sum(found.values()) if found else 0
    crashes = [d for d in os.listdir(CRASHES) if os.path.getmtime(os.path.join(CRASHES, d)) > started] if os.path.isdir(CRASHES) else []
    lines.append(f"placements in pak {total}, found in the pools {placed}")
    checks = [("every placement became a building or dummy", total > 0 and placed == total),
              ("no crash report after 30 s among the props", not crashes),
              ("IplActorsDE cleared the link flag on every pak placement", flagged[0] == flagged[1]),
              ("pak placements near the player got a UE actor", bool(actors[1]))]
    lines += [f"{'PASS' if c else 'FAIL'} {n}" for n, c in checks]
    ok = all(c for _, c in checks)
    open(OUT, "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
