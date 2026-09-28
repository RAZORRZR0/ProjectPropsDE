"""Builds ProjectPropsDE_P.pak: Project Props 4 placements for GTA SA: The Definitive Edition.

DE still runs the classic CFileLoader on Content/OriginalData/GTASA/data/gta.dat, but a new IPL line there crashes:
DE replays a baked per-IPL-file "Collision Cache" (CFileLoader LOD/collision records, dword_14572A198 == 2) and
reads past its per-file table for any file the cache does not know. So the placements are appended to the inst
sections of DE's own exterior map IPLs, after the stock lines, which leaves the cached records valid.
The 12th column is -1: LoadScene then gives them the next free slots, and IplActorsDE.asi (IplActorsDE/) spawns
runtime Unreal actors for them (DE only links cooked actors to IPL instances; without the ASI they are invisible).
Only placements of models DE already has are kept (DE cannot load new DFF/TXD/COL).

Usage: py -3 build.py <Project-Props clone> <DE install dir>
Needs repak (https://github.com/trumank/repak) on PATH or at tools/repak/repak.exe.
Writes bin/ProjectPropsDE_P.pak and bin/manifest.txt (same inputs -> same manifest and pak contents).
"""
import os, re, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPAK = shutil.which("repak") or os.path.join(HERE, "tools", "repak", "repak.exe")
ROOT = "Gameface/Content/OriginalData/GTASA/data"
MODS = os.path.join("modloader", "Project Props 4", "Project Props 4")
LOADERS = ["Stock Props", "Community Maps"]  # the mod's default set, in its loader.txt order
NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
MAX_INST = 4096  # CFileLoader::LoadScene keeps one IPL's instances in a 4096-entry stack array


def run(*a):
    return subprocess.run(a, capture_output=True, text=True, check=True).stdout


def ide_ids(folder):
    ids = set()
    for d, _, fs in os.walk(folder):
        for f in fs:
            if not f.lower().endswith(".ide"):
                continue
            sec = None
            for line in open(os.path.join(d, f), errors="replace"):
                t = [x.strip() for x in line.split("#")[0].split(",")]
                if len(t) == 1:
                    sec = None if t[0].lower() == "end" else t[0].lower()
                elif sec in ("objs", "tobj", "anim") and t[0].isdigit():
                    ids.add(int(t[0]))
    return ids


def inst_lines(path, stock):
    """The inst entries of a text IPL as 11 columns; LOD is dropped (-1): indices change once merged into a DE IPL."""
    out, dropped, sec = [], 0, None
    for line in open(path, errors="replace"):
        t = line.split("#")[0].replace(",", " ").split()
        if not t:
            continue
        if sec is None:
            sec = t[0].lower()
        elif t[0].lower() == "end":
            sec = None
        elif sec == "inst":
            nums = NUM.findall(" ".join(t[2:]))  # interior, x y z, qx qy qz qw, lod ("-0.92-1" typos split here)
            if not t[0].isdigit() or int(t[0]) not in stock or len(nums) < 8:
                dropped += 1
                continue
            out.append(f"{t[0]}, {t[1]}, {int(float(nums[0]))}, {', '.join(nums[1:8])}, -1")
    return out, dropped


def main(pp, game):
    pak = os.path.join(game, "Gameface", "Content", "Paks", "pakchunk0-WindowsNoEditor.pak")
    stock_dir, stage = os.path.join(HERE, "obj", "stock"), os.path.join(HERE, "obj", "pak")
    shutil.rmtree(os.path.join(HERE, "obj"), ignore_errors=True)
    os.makedirs(stock_dir)  # repak cannot create nested output folders
    run(REPAK, "unpack", "-q", "-f", "-o", stock_dir, "-i", ROOT, pak)
    stock = ide_ids(stock_dir)

    # hosts: exterior map IPLs that gta.dat loads and that already have text instances, so the per-file
    # entity arrays (and their numbering the cache relies on) stay as they are
    data = os.path.join(stock_dir, *ROOT.split("/"))
    listed = {l.split(None, 1)[1].strip().lower().replace("\\", "/")[5:] for l in open(os.path.join(data, "gta.dat"))
              if l.upper().startswith("IPL ")}
    hosts = {}  # path under data/ -> [text lines, next free instance index, added lines]
    for d, _, fs in os.walk(os.path.join(data, "maps")):
        for f in sorted(fs):
            rel = os.path.relpath(os.path.join(d, f), data).replace("\\", "/")
            if rel.lower() in listed and re.fullmatch(r"(?i)maps/(LA|SF|vegas|country)/\w+\.ipl", rel):
                text = open(os.path.join(d, f), "rb").read().decode("latin-1").splitlines()
                idx = [int(t[11]) for t in (l.replace(",", " ").split() for l in text) if len(t) == 12 and t[11].isdigit()]
                if idx:
                    hosts[rel] = [text, max(idx) + 1, []]

    manifest = []
    for group in LOADERS:
        folder = os.path.join(pp, MODS, group)
        for l in open(os.path.join(folder, "loader.txt"), errors="replace"):
            if not l.upper().startswith("IPL "):
                continue
            name = l.split(None, 1)[1].strip().split("/")[-1]
            insts, dropped = inst_lines(os.path.join(folder, "maps", name), stock)
            host = min(sorted(hosts), key=lambda h: hosts[h][1] + len(hosts[h][2]))
            h = hosts[host]
            h[2] += [f"{s}, -1" for s in insts]
            assert h[1] + len(h[2]) <= MAX_INST, (host, name)
            manifest.append(f"{len(insts):5d} placed  {dropped:4d} dropped  {group}/{name} -> {host}")

    for rel, (text, _, added) in sorted(hosts.items()):
        if not added:
            continue
        low = [l.strip().lower() for l in text]
        end = low.index("end", low.index("inst"))
        out = os.path.join(stage, *ROOT.split("/"), *rel.split("/"))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        open(out, "wb").write(("\r\n".join(text[:end] + added + text[end:]) + "\r\n").encode("latin-1"))

    os.makedirs(os.path.join(HERE, "bin"), exist_ok=True)
    target = os.path.join(HERE, "bin", "ProjectPropsDE_P.pak")
    run(REPAK, "pack", "--version", "V11", "--mount-point", "../../../", stage, target)
    manifest.append(f"total {sum(int(m.split()[0]) for m in manifest)} placements in {sum(1 for h in hosts.values() if h[2])} DE IPLs")
    open(os.path.join(HERE, "bin", "manifest.txt"), "w").write("\n".join(manifest) + "\n")
    print(manifest[-1], "->", target)


if __name__ == "__main__":
    main(*sys.argv[1:3])
