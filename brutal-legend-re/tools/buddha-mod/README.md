# Buddha Mod Loader

A minimal DLL injection mod loader for Brutal Legend. Hooks the game's file I/O so that content placed in `Win/Mods/` can override files in `Win/Packs/`.

## Files

| File | Purpose |
|------|---------|
| `buddha_mod.cpp` | The mod loader DLL (hooks CreateFileA/W via IAT) |
| `load_mod.cpp` | Injector that launches the game and loads the DLL |
| `README.md` | This file |

## How It Works

1. `load_mod.exe` starts Brutal Legend and injects `buddha_mod.dll` into the process.
2. `buddha_mod.dll` hooks `CreateFileA` / `CreateFileW` via the Import Address Table (IAT).
3. When the game requests a file under `Win\` or `Data\`, the hook checks `Win/Mods/<path>`.
4. If a mod file exists at that path, the hook redirects the file open to it; otherwise it falls through to the original call.

**Limitation:** This is a coarse-grained hook on Win32 `CreateFile`. The more precise approach is to hook `GSysFile::Open()` directly in the Buddha engine vtable, which requires Ghidra analysis to find the vtable offset (see below).

## Building

### Automatic (recommended)

Double-click `build.bat`. It auto-detects g++ or MSVC and builds both files.

```
build.bat          # auto-detect compiler
build.bat g++      # force MinGW
build.bat msvc     # force MSVC
```

Output goes to `bin/buddha_mod.dll` and `bin/load_mod.exe`.

### Manual Build

**With g++ (MinGW-w64):**

```bat
:: Build the DLL
g++ -shared -O2 -Wall buddha_mod.cpp -o buddha_mod.dll -nostdlib -lkernel32 -luser32

:: Build the injector
g++ -O2 -Wall load_mod.cpp -o load_mod.exe -lkernel32 -luser32
```

**With Visual Studio Developer Command Prompt:**

```bat
:: Build the DLL
cl /LD /EHsc /O2 /W3 buddha_mod.cpp /Fe:buddha_mod.dll kernel32.lib user32.lib

:: Build the injector
cl /EHsc /O2 /W3 load_mod.cpp /Fe:load_mod.exe kernel32.lib user32.lib
```

### Requirements

- **32-bit build** — the game is x86. Your compiler must produce 32-bit binaries.
- For MinGW: use `i686` or `i686-w64-mingw32` variant.
- For MSVC: use the x86 Developer Command Prompt (not x64).

### Notes

- No Steam SDK or game libraries needed — only Win32 API.
- The hook approach (CreateFileA/W IAT) was confirmed from import analysis of `BrutalLegend.exe` — no Steam documentation used.

## Installation

1. Place `buddha_mod.dll` **in the same directory as `BrutalLegend.exe`**:
   ```
   <game_dir>\
   ├── BrutalLegend.exe
   ├── buddha_mod.dll    <-- here
   └── ...
   ```

2. Create the mod override directory:
   ```
   <game_dir>\Win\Mods\
   ```

3. (Optional) Build and place `load_mod.exe` anywhere you like.

## Usage

### Option A: Use the injector (recommended)

Run `load_mod.exe` without arguments to launch the game and inject the mod loader:

```
load_mod.exe
```

You can also point it at a specific executable:

```
load_mod.exe "C:\Path\To\BrutalLegend.exe"
```

### Option B: Manual injection

Use a third-party injector (e.g., [KSF](https://github.com/A，工程-Delta/KSF-Injector)) to load `buddha_mod.dll` into `BrutalLegend.exe`.

## Creating Mods

Place overridden bundle files inside `Win/Mods/` matching the path structure of the original files in `Win/Packs/`.

**Example: Override a texture**

If the original file is:
```
Win\Packs\Man_Trivial.~p
```

Create a modified `Man_Trivial.~p` and place it at:
```
Win\Mods\Man_Trivial.~p
```

The mod file will be opened in place of the original.

**Example: Add a custom bundle**

Drop a new bundle at:
```
Win\Mods\MyMod.~h
Win\Mods\MyMod.~p
```

## Debugging

`buddha_mod.dll` writes a log file `buddha_mod.log` next to `BrutalLegend.exe` on load. It records:
- The game directory
- The mod directory path
- Which hook is active

## Finding the GSysFile::Open() Address (Next Step)

The current implementation hooks `CreateFileA/W`, which covers most file opens but may miss memory-mapped or custom file I/O paths used by `GSysFile`.

To hook `GSysFile::Open` directly:

1. Load `BrutalLegend.exe` in **Ghidra**.
2. Find the `GSysFile` class:
   - Search for string references to `"GSysFile"` or `"GSysFile::Open"`.
   - Alternatively, find the vtable by looking at RTTI (Run-Time Type Information) references.
3. The vtable offset for `Open()` is typically around **0xXX** (Ghidra will show the vtable layout).
4. Implement a vtable hook in `buddha_mod.cpp`:
   ```cpp
   // After LoadLibrary + GetProcAddress on Buddha.exe:
   void** vtable = *(void***)(gsysfile_instance);
   HookVTable(vtable, OPEN_VTABLE_OFFSET, hooked_gsysfile_open, &orig_gsysfile_open);
   ```
5. Replace the `CreateFileA/W` IAT hook with the vtable hook.

See `docs/MOD_LOADER_ARCHITECTURE.md` for the full engine analysis and `docs/engine/IMPORT_ANALYSIS.md` for Buddha.exe export details.

## Limitations

- **No Steam Workshop support** - this is a basic file override system only.
- **No hot-reload** - changes require a game restart.
- **No mod manifest** - all files in `Win/Mods/` are loaded unconditionally.
- **No bundle unpacking** - place full `.~h` / `.~p` bundle pairs in `Win/Mods/`.
- **x86 only** - the game is 32-bit; both the DLL and injector must be compiled as 32-bit.

## File Structure

```
buddha-mod/
├── buddha_mod.cpp   <- the DLL hook (IAT hook on CreateFileA/W)
├── load_mod.cpp     <- the injector (CreateRemoteThread + LoadLibrary)
├── build.bat        <- build script (auto-detects g++ or MSVC)
└── README.md         <- this file
```

## Game Paths

- **Steam**: `<STEAM_PATH>\steamapps\common\BrutalLegend\`
- **Default**: `Win/Packs/` (game bundles)
- **Mods**: `Win/Mods/` (override bundles)
- **Logs**: `buddha_mod.log` (written next to `BrutalLegend.exe`)
