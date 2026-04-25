# Buddha Engine Architecture

**Status:** 🔴 Planning  
**Game:** Brutal Legend (2009)  
**Engine:** Buddha (Double Fine proprietary)  

---

## Engine Overview

Buddha is Double Fine's custom in-house game engine used across multiple titles from Psychonauts (2005) through later games.

---

## Middleware Components

| Component | Purpose | Evidence |
|-----------|---------|----------|
| **FMOD** | Audio system | FSB audio banks, confirmed from DoubleFine Explorer |
| **Havok Physics** | Physics simulation | Standard middleware for 2009 era |
| **Havok Animations** | Animation System | BL uses a Custom Wrapper |
| **Scaleform GFx** | UI system | Common in EA published games |
| **Bink Video** | Cutscenes | Standard video codec |
| **ZLib** | Compression | Confirmed in DFPF format |
| **Lua** | Scripting | Game scripts in .lua format |

---

## File Format Summary

| Extension | Type | Editable |
|-----------|------|----------|
| `.~h` / `.~p` | DFPF container pairs | Yes (with tools) |
| `.proto` | Prototype definitions | Yes (text) |
| `.lua` | Script files | Yes |
| `.fsb` | FMOD audio banks | Partial |
| `.dds` | Textures | Yes (replace) |
| `.bik` | Bink video | No |

---

## Game Architecture

```
BrutalLegend.exe
    │
    ├── DFPF Loader ──→ .~h/.~p bundles
    │       │
    │       ├── Man_Script.~h/.~p (Lua scripts)
    │       ├── Man_Trivial.~h/.~p (Models, textures)
    │       ├── 00Startup.~h/.~p (Core prototypes)
    │       └── [Other bundles]
    │
    ├── Lua Engine ──→ Mission scripts, game logic
    │
    ├── FMOD ──→ Audio playback
    │
    ├── Havok ──→ Physics simulation
    │
    └── Renderer ──→ OpenGL/DirectX 9 (PC version)
```

---

## Key Systems

### 1. Prototype System
- Defined in `all.proto`
- Controls units, characters, vehicles
- Text-editable with proper format knowledge
- Allows character/unit swaps

### 2. Mission System
- Lua-based mission scripts
- Triggers, objectives, rewards
- Linear story progression with side missions

### 3. Stage Battle (RTS)
- Real-time strategy combat
- Three factions: Ironheade, Drowning Doom, Tainted Coil
- Data-driven unit stats

### 4. Open World
- ~40 square miles streaming world
- Zone-based loading
- Vehicle traversal (The Deuce)

---

## Modding Capabilities

| Feature | Supported |
|---------|-----------|
| Character swaps | ✅ Yes |
| Faction swaps | ✅ Yes |
| Texture replacement | ✅ Yes |
| Audio replacement | ✅ Yes |
| New Animations | 🔴 No (format and repacking to game not parsed) |
| New missions | 🔴 No (undocumented) |
| New maps | 🔴 No (undocumented) |
| New characters | 🔴 No (prototype limit) |

---

## Toolchain

| Tool | Purpose |
|------|---------|
| Ghidra | Executable disassembly |
| x64dbg | Dynamic debugging |
| ImHex | Binary analysis |
| Kaitai Struct | Format specifications |
| DoubleFine Explorer | Asset extraction |

---

## TODO

- [ ] Document all function addresses
- [ ] Map complete class hierarchy
- [ ] Document save file format
- [ ] Find memory structures
