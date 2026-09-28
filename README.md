# ProjectPropsDE

Port of [Project Props 4](https://github.com/user-grinch/Project-Props) (classic GTA SA map-prop mod) to
**GTA San Andreas – The Definitive Edition**, plus **IplActorsDE**, the ASI that makes new map props visible in DE.

Status: 16,166 props load, collide and render. Tested on `SanAndreas.exe` SHA-256 `ed7545eb…ac1f0` and
`cf677214…5ba17`; the ASIs find the game code by byte signature and refuse to install on builds they don't recognise.

| Piece | State |
|---|---|
| `build.py` → `bin/ProjectPropsDE_P.pak` | 16,166 placements, stock models only, 12th column `-1` |
| Rendering | [IplActorsDE](IplActorsDE) (generic: any map mod using the `-1` convention) |
| Pool / matrix limits | [DE_LimitAdjuster](https://github.com/RAZORRZR0/DE_LimitAdjuster) with `DE_LimitAdjuster.ini` from this repo |
| Custom models (new DFF/TXD/COL), `procobj.dat`, `object.dat` | Not portable: DE has no `CStreaming::AddImageToList` |

## Install (players)

Needs an ASI loader in `Gameface\Binaries\Win64\` (e.g. Ultimate ASI Loader).

1. `ProjectPropsDE_P.pak` → `Gameface\Content\Paks\~mods\`
2. `IplActorsDE.asi` → `Gameface\Binaries\Win64\` (or wherever your ASI loader loads ASIs from)
3. `DE_LimitAdjuster.asi` **and this repo's `DE_LimitAdjuster.ini`** → the same folder as each other.
   Without the ini the game crashes while loading the props (`DE_LimitAdjuster.log` then says `ini not found`).

Check `IplActorsDE.log` says `hooked LoadObjectInstance` and `DE_LimitAdjuster.log` shows lines like
`PtrNodeDouble: 7500 -> 20000`. If either says `unsupported SanAndreas.exe`, remove the pak.

## Build (modders)

```
py -3 build.py <Project-Props clone> "D:/GTA SA/GTA San Andreas - Definitive Edition"
IplActorsDE\build.bat
```

`build.py` needs [repak](https://github.com/trumank/repak) on PATH (or at `tools/repak/repak.exe`). It reads the
placements from your Project Props clone and DE's own map files from your game's `pakchunk0`, so this repo contains
no Project Props or Rockstar data. `bin/manifest.txt` lists every Project Props IPL, how many placements it kept,
and the DE IPL it went into.

## What goes into the pak

Only the mod's default set: the IPLs named in `Stock Props/loader.txt` and `Community Maps/loader.txt`, keeping
placements whose model id exists in DE's IDEs (all 16,166 do; the model *name* in the line is ignored by the game).
The Urbanize/BDL/LOD-tree compatibility variants, custom models, procedural objects and `object.dat` tweaks are left out.

## Reverse-engineering notes

All addresses are VAs in `SanAndreas.exe` `ed7545eb…ac1f0` (image base `0x140000000`); in `cf677214…` code is +0x1490.

### Loading: DE still runs the classic loader

- `CFileLoader::LoadLevel` `0x1411319D0` parses `DATA\GTA.DAT` (called from `0x141208980`, state 8). Files come from
  `Content/OriginalData/GTASA/` through UE's file system (`CFileMgr::OpenFile` `0x140ADA8C0`), so a `~mods` pak can
  override them. `IMG` lines only log `Must implement CStreaming::AddImageToList`: no new models.
- `CFileLoader::LoadScene` `0x141134A20` reads text IPLs. `inst` lines go to `0x1411400C0`
  (`"%d %s %d %f %f %f %f %f %f %f %d %d"`); DE's 12th column is the instance index inside the file, packed into the
  high word of the model id. Instances sit in a **4096-entry stack array** per file.
- `CFileLoader::LoadObjectInstance` `0x141140270`: object.dat models become a `CDummy` (pool `0x14572A578`, 120 B),
  everything else a `CBuilding` (pool `0x14572A588`, 112 B). Tilted instances (`|qx|` or `|qy|` > 0.05) take a
  permanent matrix (`0x14116B860`).

### Why new IPL files crash: the baked collision cache

`sub_14103C9E0` loads a cooked "Collision Cache" asset. When it isn't empty (`dword_14572A198 == 2`), every text IPL
replays that cache's per-file records at the end of `LoadScene` (`0x141136E30` → `0x14103CE70`), indexed by a running
file counter. An IPL file the cache doesn't know reads past the per-file table → access violation.
**So the pak adds no IPL files**: it appends the placements to the `inst` sections of 20 of DE's own exterior IPLs,
after each file's highest explicit index, which leaves every cached record valid.

### Why they were invisible: the IPL actor-link flag

Visible map props are cooked Unreal actors (`AIPLMapActor`, `GTABase_classes.hpp:5570`, fields `OriginalDFF`,
`IplIndex`, `bEntityLinkActor`), not RW geometry. The RW entity finds its actor in `CEntity::CreateRwObject`
(vtable slot `+0x08`, `0x14112DF90`):

| Entity field | Meaning |
|---|---|
| `+0x20` | the UE actor/component (null = nothing drawn) |
| `+0x34` bit 3 (`0x08`) | "IPL entity: link to the baked actor". Set by `LoadObjectInstance` (`|= 8 * fromIpl`, always 1 for text IPLs) |
| `+0x34` bit 2 (`0x04`) | link request already queued |
| `+0x58` | IplIndex (the 12th column) |

- **Bit 3 set** (every IPL entity): `CreateRwObject` resolves the model's soft actor class (`ModelInfo +0x58`), and if it
  is a `DynamicIPLMapActor` calls `0x140AF3280(world, entity, pos·100 (Y flipped), model, IplIndex)`. That looks up
  `IplIndex·12345 + model` in a map of registered cooked actors and otherwise queues the entity (`0x140B07A40`)
  until such an actor registers. For a new placement none ever does: `+0x20` stays null.
- **Bit 3 clear** (script objects, anything created at runtime): `CreateRwObject` calls `ModelInfo` vtable `+0x60`
  (`CreateInstance(matrix, …)`), which builds a UE actor for the model on the spot and stores it in `+0x20`.

Found by classifying the 30 non-trivial callers of `IPLMapActor::StaticClass` (`0x140B637C0`),
`DynamicIPLMapActor::StaticClass` (`0x140C7C3E0`) and the `CBuilding` vtable (`0x144304F50`) with a frozen rubric,
then reading the flagged ones.

Verified in game (`test/e2e_props.py`): with bit 3 cleared on the pak's entities at load (IplActorsDE), moving next
to them gives them UE actors and they draw (road barriers, box pile, fences at the Angel Pine motel). Without it the
same spot is empty and only the collision is there.

### Limits the mod hits

| Limit | DE | Needed | Failure |
|---|---|---|---|
| Dummys / Buildings | 8500 / 14000 | 10197 / 9832 at load | pool full → null entity |
| PtrNodeDouble | 7500 | ~13500 | sector lists |
| EntryInfoNode | 600 | 600 reached driving around | crash in `0x14115BCA0` |
| MatrixList | 1800 | 1,066 permanent + live objects | `GetMatrix` steals from an empty list: crash in `0x14116B9C0` |

## Test

`py -3.12 test/e2e_props.py` (pak installed, game closed, save loads into gameplay; installs `IplActorsDE.asi`).
Checks: all 16,166 placements are entities, IplActorsDE cleared the link flag on all of them, the ones near the
player got a UE actor, no crash report after 30 s among the props. Writes `test/e2e_props.txt`.

Not yet explained: of the ~83 placements within 60 m of the test spot, 19 carry an actor in `+0x20`; the rest are
likely object.dat dummies (which spawn a separate `CObject`) or beyond their model's draw distance.

## Credits

- **Project Props** and all its placements: [user-grinch/Project-Props](https://github.com/user-grinch/Project-Props).
  Grinch_ and Zeneric (Project Props 4 Community), Reaper, Marchewa99XD, James Harlet, LandoF, Matslick,
  Endochronic, mixsylent (Objectopia), lanldsd (More Vegetation), Yutte, CatchyKetchup, KaiQ and Davve95
  (2.2 Fixes), and every contributor listed in the Project Props README. This repo only converts their work for DE;
  it ships none of it. Please ask the Project Props team before redistributing a built pak.
- **Tsuda Kageyu**: [MinHook](https://github.com/TsudaKageyu/minhook) (BSD-2, license in `IplActorsDE/minhook/MinHook.h`).
- **trumank**: [repak](https://github.com/trumank/repak), used by `build.py` to read and write DE's `.pak` files.
- **Encryqed** and contributors: [Dumper-7](https://github.com/Encryqed/Dumper-7); its dump of DE's Unreal SDK
  showed the `AIPLMapActor` / `IplIndex` link that IplActorsDE works around.
- **ThirteenAG, LINK/2012** and contributors: [Open Limit Adjuster](https://github.com/GTAmodding/III.VC.SA.LimitAdjuster),
  which [DE_LimitAdjuster](https://github.com/RAZORRZR0/DE_LimitAdjuster) ports.
- DE port, reverse engineering and IplActorsDE: RAZORRZR0.

Grand Theft Auto and GTA San Andreas are trademarks of Take-Two Interactive / Rockstar Games.

## License

Code in this repo (`build.py`, `IplActorsDE`, tests): MIT, see `LICENSE`. MinHook keeps its own BSD-2 license.
The Project Props placements belong to their authors and are not covered by this license.
