# IplActorsDE

x64 ASI for **GTA San Andreas – The Definitive Edition** that lets map mods add props with plain text IPL lines.
Not tied to Project Props: any mod that follows the convention below gets visible props.

## The problem it solves

DE draws map props with cooked Unreal actors (`AIPLMapActor`) and links each RW map entity to its actor by
`(IplIndex, model)`. `CFileLoader::LoadObjectInstance` marks every IPL instance for that link (entity `+0x34` bit 3),
so a new placement waits forever for a cooked actor that doesn't exist: it collides but is invisible.
With the bit clear, `CEntity::CreateRwObject` builds an actor for the model at runtime, the way it does for
script-created objects. Full RE notes: [`../README.md`](../README.md).

## Convention for mods

Give the `inst` line a **12th column of `-1`**:

```
1422, DYN_ROADBARRIER_5, 0, -2206.07, -2259.11, 30.11, 0, 0, 0.7071, 0.7071, -1, -1
```

- DE's own IPLs never use a negative index, so stock placements are untouched.
- Only lines read by `CFileLoader::LoadScene` (text IPLs listed in `gta.dat`) are affected, not stream IPLs.
- `-1` also tells `LoadScene` to put the instance in the next free slot of the file, after the stock ones.

Rules the game imposes regardless of this ASI (details in the Project Props notes):

- Append to DE's existing IPLs (via a `~mods` pak overriding `Content/OriginalData/GTASA/data/maps/...`).
  A new `IPL` line in `gta.dat` crashes at load (baked collision cache).
- At most 4096 instances per IPL file (`LoadScene` stack array).
- Stock models only; DE cannot load new DFF/TXD/COL.
- Many props need bigger pools: [DE_LimitAdjuster](https://github.com/RAZORRZR0/DE_LimitAdjuster) (`Dummys`, `Buildings`, `PtrNode*`,
  `EntryInfoNode`, `ColModel`, `MatrixList`).

## How it works

MinHook on `CFileLoader::LoadObjectInstance` (text form). After the original returns, if the caller is `LoadScene`
and the line's 12th token is `-1`, it clears bit 3 of entity `+0x34`.
All three addresses come from byte signatures (`src/sigscan.h`, each must match exactly once): the function head,
its call in `LoadScene` (whose target must equal that head), and `and dword [rbx+34h], ~8` in the instance builder
(proves the flag still lives at `+0x34` bit 3). Any miss: logs "unsupported SanAndreas.exe" and installs nothing.
Checked on `SanAndreas.exe` `ed7545eb…ac1f0` and `cf677214…5ba17`.

`IplActorsDE.log` (next to the ASI) logs the hook and every 1000th marked placement.

## Build / install

`build.bat` (VS 2022 x64 build tools; MinHook in `minhook/`) → `bin\IplActorsDE.asi`.
Copy it to `<Game>\Gameface\Binaries\Win64\` (needs an ASI loader).

## Test

`../test/e2e_props.py` installs the ASI, loads the game with the Project Props pak and checks that
all 16,166 `-1` placements have the flag cleared and that the ones near the player got a UE actor.
