# Brutal Legend Test Map Pipeline

A minimal custom map creation pipeline for Brutal Legend modding.

## Overview

This pipeline creates a test map tile that can be loaded by Brutal Legend through the mod loader. The tile uses coordinates **x=100, y=100**, which are outside the normal continent3 range (x=-8 to +6, y=-8 to +7), ensuring no conflict with real terrain.

## Files

| File | Purpose |
|------|---------|
| `create_test_map.py` | Creates the test map bundle |
| `load_test_map.bat` | Copies bundle to Win/Mods/ and optionally launches game |
| `README.md` | This documentation |

## Quick Start

### 1. Prerequisites

- Python 3.6+
- Brutal Legend installed
- Mod loader (buddha_mod.dll) installed in game directory

### 2. Create the Test Map

```bash
cd tools/map-pipeline
python create_test_map.py
```

This creates a `test_map/` directory containing:
- `RgS_Testworld.~h` - DFPF header file
- `RgS_Testworld.~p` - DFPF data file

### 3. Load the Test Map

```bat
load_test_map.bat
```

Or manually copy the files:
```bat
copy test_map\RgS_Testworld.* "<STEAM_PATH>\steamapps\common\BrutalLegend\Win\Mods\"
```

### 4. Launch the Game

Run through the mod loader:
```bat
load_mod.exe
```

Or if using manual injection, launch `BrutalLegend.exe` with your injector.

## Full Pipeline

### Extract Original Tile

Extract a tile from the game bundles:

```bash
cd tools/dfpf-toolkit
python dfpf_extract.py /path/to/RgS_World.~h
```

This extracts to `RgS_World_extracted/`.

### Modify with Terrain Editor

Edit the extracted heightfield:

```bash
cd tools/terrain-editor
python terrain_editor.py edit-height \
    input.Heightfield \
    output.Heightfield \
    --x1 0 --y1 0 --x2 64 --y2 64 --delta 20
```

### Repack Bundle

Repack the modified files:

```bash
cd tools/dfpf-toolkit
python dfpf_repack.py \
    /path/to/RgS_World.~h \
    /path/to/RgS_World_extracted \
    RgS_World_modified
```

### Load Through Mod Loader

Copy repacked bundle to mods directory:

```bat
copy RgS_World_modified.* "C:\game\Win\Mods\"
```

### Test in Multiplayer

The mod loader intercepts file requests at:
- `GSysFile::Open()` level (preferred, if hooked)
- `CreateFileA/W` level (fallback)

If a file isn't found in `Win/Mods/`, it falls through to the original `Win/Packs/` files.

## Tile Coordinate System

### World Structure

Tiles are organized as:
```
worlds/<worldname>/tile/x<coord>/y<coord>/<layer>.<type>
```

### Known Worlds

| World | X Range | Y Range | Description |
|-------|---------|---------|-------------|
| continent3 | -8 to +6 | -8 to +7 | Main campaign |
| dlc1_4 | varies | varies | DLC terrain |
| sk_1, sk_2, etc. | varies | varies | Skiply regions |

### Tile Layers

| Layer | Type | Description |
|-------|------|-------------|
| height | bin | Heightfield data (HSEM format) |
| blend | bin | Terrain blend texture data |
| blend | Texture | Blend texture metadata |
| occlusion | bin/Texture | Ambient occlusion |
| base_tile | bin | Collision mesh (Havok) |
| base_ptile | bin | Pathfinding grid |

## Test Map Details

The test map creates a single tile at x=100, y=100 with:

- **height.bin** - Minimal HSEM format with flat height values
- **blend.bin** - Simple 2-material blend pattern
- **blend.Texture** - References sandbeach terrain material
- **occlusion.Texture** - Minimal occlusion data

This is intentionally minimal to test:
1. DFPF container loading
2. Tile path resolution
3. File format parsing
4. Graceful failure if formats are incorrect

## Troubleshooting

### Mod loader not active
- Check for `buddha_mod.log` in game directory
- Verify `buddha_mod.dll` is in the same directory as `BrutalLegend.exe`

### Game crashes on load
- The tile format may be incorrect
- Try validating game files through Steam
- Check game logs for specific errors

### Tile not appearing
- Ensure coordinates don't overlap with real tiles
- The game may have bounds checking that rejects out-of-range tiles
- Verify bundle files are in `Win/Mods/` (not a subdirectory)

## Technical Notes

### DFPF V5 Format

Container format used by Brutal Legend:
- `.~h` file contains header/index
- `.~p` file contains actual data
- Big-endian byte order
- ZLIB compression for most files

### Heightfield Format

Brutal Legend uses a custom heightfield format:
- 40-byte custom header
- DDS texture (DXT5) with height in alpha channel
- Processed by GPU shader for displacement

### hsEm Format

Some files use "hsem" (mesh backwards) container:
- Header with metadata floats
- "lrtm" terrain marker
- Material index data

## References

- [DFPF Format Spec](../../docs/formats/DFPF_SPEC.md)
- [Terrain Format Spec](../../docs/formats/TERRAIN_SPEC.md)
- [Buddha Mod Loader](../buddha-mod/README.md)
