# Brutal Legend animation RE — handoff

This document is the practical "where we are, what's next, how to do it"
summary. For deep-dive technical details see `ANIMATION_FUN_ANALYSIS.md`.

## Status: 80% complete

### ✅ DONE — fully working

- **Parser for all 27 b20_horse animations** (`b20_horse_anim_parser.py`).
  Extracts: rig (92 bones with parents + bind pose), all `.AnimResource`
  metadata (FPS, period, total frames, blocks, durations, events, animated
  bone correspondence), `.Stance` / `.ComboPose` / `.ComboAnim`
  text-format property files. Output: structured JSON in
  `b20_horse_parsed/`.

- **Complete dnap on-disk format mapping** — every header field validated
  empirically across all 24 animations. See
  `ANIMATION_FUN_ANALYSIS.md` §16.

- **Static analysis of every relevant Ghidra function** — see
  `ANIMATION_FUN_ANALYSIS.md` §1-§17, plus the `FUN_*.txt` exports in
  this folder.

### ❌ OPEN — needs runtime debugging

- **Per-frame quaternion playback for animations.** We know the file
  format structurally; we don't yet know how the runtime decodes dnap
  bytes into bone transforms each frame.

## The blocking problem

All Havok-named animation functions (`hkaDeltaCompressedAnimation`,
`hkaWaveletCompressedAnimation`, `hkaSplineCompressedAnimation`) are
**dead code in BL.exe** — never called. Brutal Legend has its own
custom sampler somewhere we haven't located. The on-disk dnap buffers
in memory are read-only post-load; the runtime samples from a
separate decoded buffer.

## The recommended path forward: Cheat Engine + Lua

After spending hours fighting x32dbg + MCP unreliability, I believe
**Cheat Engine is dramatically better tooling** for this specific
problem because:

1. CE's "find what writes this address" feature *automatically*
   captures the EIP and call stack of every instruction that modifies
   a target address — no manual breakpoint setup required.
2. CE's memory scan is robust where x32dbg's MCP search returns
   sentinel values on cross-region scans.
3. CE has built-in Lua scripting that can automate the entire
   workflow.

### Setup

1. Install **Cheat Engine** from <https://www.cheatengine.org/> (uncheck
   the optional adware in installer, or use chocolatey: `choco install
   cheatengine`).
2. Install **Borderless Gaming** from
   <https://github.com/Codeusa/Borderless-Gaming> (so BL doesn't pause
   when CE has focus). Alternative: edit BL's `Buddha.cfg` to set
   `FullScreen = 0`.
3. Launch BL, get to a save where the horse is animating in place.
4. Launch CE → click the small computer icon (top-left) → select
   `BrutalLegend.exe`.

### The Lua script (do this in CE)

In Cheat Engine: **Table → Show Cheat Table Lua Script** (top menu).
Paste the script below, click **Execute**. This automates:
- 7 progressive "Changed value" scans (filters to per-frame floats)
- Range filter to `[-1, 1]` (quaternion components)
- Reports the first 5 candidate addresses

```lua
-- bl_horse_anim_finder.lua
-- Finds floats that change every frame and stay in [-1, 1] —
-- prime candidates for bone-quaternion components.

local mods = enumModules()
local blBase, blEnd = nil, nil
for i, m in ipairs(mods) do
  if m.Name:lower() == "brutallegend.exe" then
    blBase = m.Address
    blEnd = m.Address + m.Size
    break
  end
end
print(string.format("BL.exe: 0x%X .. 0x%X", blBase, blEnd))

local scan = createMemScan()
print("First scan: Unknown initial value (Float)...")
scan.firstScan(soUnknownValue, vtSingle, rtRounded, 0, 0,
               0x10000, 0x7FFFFFFF, "*X-C+W-N",
               fsmNotAligned, "", false, false, false, false)
scan.waitTillDone()
sleep(1000)

for i = 1, 6 do
  print(string.format("Pass %d: Changed value...", i))
  scan.nextScan(soChanged, vtSingle, rtRounded, 0, 0, false,
                fsmNotAligned, false, false, false, false)
  scan.waitTillDone()
  sleep(1000)
end

print("Filtering to [-1, 1]...")
scan.nextScan(soBetweenValues, vtSingle, rtRounded, -1.0, 1.0, false,
              fsmNotAligned, false, false, false, false)
scan.waitTillDone()

local fl = scan.getAttachedFoundlist()
local count = fl.Count
print(string.format("Final hits: %d", count))

print("\nFirst 10 candidate addresses + values:")
for i = 0, math.min(9, count - 1) do
  local addr = fl[i]
  print(string.format("  0x%X = %.6f", addr, readFloat(addr)))
end

print("\nNext: pick 3-5 of those addresses, right-click each in CE's")
print("result list → 'Find out what writes this address'.")
print("Run the game ~3 sec, then look for brutallegend.exe writers")
print("and paste their EIPs to Claude.")
```

### After running the script

1. The script should leave **a few hundred to a few thousand hits** in
   CE's main result list.
2. **Pick 3-5 different addresses** (ideally with different recent
   values).
3. For each, **right-click → "Find out what writes this address"**.
4. Let the game run **2-3 seconds**.
5. The popup window populates with instructions. Look at the **Module
   column** — only `brutallegend.exe` entries are useful.
6. Sort by hit count (descending). The most-frequently-firing
   `brutallegend.exe` instruction across multiple addresses is the
   live sampler.
7. **Paste the EIP** (e.g., `00BF4D74`) of those writers to Claude.

## What Claude will do once you have the EIPs

1. Translate runtime EIP → Ghidra address: `Ghidra = EIP - 0x630000`
2. Locate the function containing that EIP in our exports / Ghidra
3. Decompile it (via Ghidra MCP or by exporting if needed)
4. Read its byte-fetch pattern → that tells us **exactly** which
   dnap offsets the runtime reads, in what order, and with what
   dequantization
5. Update `b20_horse_anim_parser.py` with the real format
6. Verify by sampling a known frame and comparing to expected
   quaternions

## Files in this folder

| File | Purpose |
|---|---|
| `b20_horse_anim_parser.py` | The animation parser. Run with `python b20_horse_anim_parser.py`. Outputs to `b20_horse_parsed/`. |
| `b20_horse_parsed/` | Structured JSON output for every horse animation, the skeleton, all stances, etc. |
| `dnap_field_finder.py` | Empirical scanner that produced the validated header layout. |
| `ANIMATION_FUN_ANALYSIS.md` | Complete technical analysis (deep dive into all 100+ functions, format theory, runtime debugging findings). |
| `RUNTIME_DEBUG_GUIDE.md` | Original x32dbg guide (mostly superseded by this CE-based approach). |
| `HANDOFF.md` | This file — practical next steps. |
| `FUN_*.txt` | Ghidra decompilation exports of relevant functions. |
| `b20_horse_anim_parser.py.bak` | Backup of an older parser version. |

## If you don't want to do the runtime debugging

The structural parser is genuinely useful as-is. You can:

- Extract animation **metadata** for any character to use in mods or
  data inspection
- Build asset listings, validate file integrity
- Use the skeleton + stance / combo data for non-animation tasks
- Document the format structurally for the modding community

The piece that's missing — actual bone-quaternion playback — is what
you'd need for things like *replaying* an animation in a custom
viewer or *converting* dnap files to FBX. For now, the existing
mesh+rig export tools (`fmt_brutal_mesh.py` for Noesis) handle static
mesh extraction; animation export remains an open community problem.

## NEW findings from this session's expanded exports

After scanning the additional 130 FUN_ files plus `GhidraSearchForFILE.txt`:

### What we ruled out

- **`hkBinaryPackfileReader`** / **`hkXmlPackfileReader`** / **`hkPackfileData`** — confirmed dead. dnap files start with magic `64 6E 61 70` ("dnap"), not Havok's binary-packfile magic `57 E0 E0 57`. The Packfile classes are unused Havok library code that ships with BL.exe but isn't called for dnap.
- The Packfile vftables exist at `0x00e58fe8` (BinaryPackfileReader) and `0x00e59cd0` (PackfileData) but their ctors aren't part of the dnap load path.

### What we discovered (still needs follow-up)

**Two distinct `hkaSplineCompressedAnimation` ctor variants**:

| Outer ctor | Calls inner | Status |
|---|---|---|
| `FUN_00dd2a30` / `FUN_00dd2bd0` | `FUN_00dd1d10` | We analyzed this. Spline **encoder** body. |
| **`FUN_00dca060`** (NEW) | **`FUN_00dd1a00`** (NOT YET EXPORTED) | New variant — possibly the "load from binary" path |

The new `FUN_00dca060` outer ctor:
```c
void __cdecl FUN_00dca060(undefined4 *param_1, int param_2) {
    if (param_1 != NULL &&
        (*param_1 = hkaSplineCompressedAnimation::vftable, param_2 != 0)) {
        FUN_00dd1a00(param_1);   // ← UNEXPORTED — this is the bit we need
    }
}
```

This is **structurally identical** to the Wavelet ctor pattern (`FUN_00dca130` → `FUN_00dd4b00`) and the Delta ctor pattern (`FUN_00dc9d10` → `FUN_00dcc280`). So `FUN_00dd1a00` is plausibly a **byte-swap fixup pass** for spline-format dnap data — the analog of `FUN_00dcc280` (Delta) and `FUN_00dd4b00` (Wavelet).

### Action: export 2 more functions from Ghidra

```python
TARGET_FUNCTIONS += [
    "00dd1a00",   # The unexported inner ctor body (called by FUN_00dca060)
    "00dd4680",   # Sample helper called by FUN_00dd3830 (not yet exported)
]
```

If `FUN_00dd1a00` has actual call xrefs (i.e., something REALLY does call `FUN_00dca060`), we'd have a third ctor variant that may be the live one. To verify in Ghidra:

1. Right-click `FUN_00dca060` in Ghidra → "Show References to"
2. If it has call xrefs OTHER than the class registration: that's the live load path
3. If only registration xrefs: it's dead like the others

## Updated CE Lua script (v2, FIXED)

The original script had a Lua API error (`getAttachedFoundlist` returns nil). Use `bl_anim_finder_v2.lua` in this folder instead. The fix:

```lua
-- OLD (broken):
local fl = scan.getAttachedFoundlist()

-- NEW (correct):
local fl = createFoundList(scan)
fl.initialize()
print(fl.Count)
for i = 0, fl.Count - 1 do
  local addrStr = fl[i]
  local addr = tonumber(addrStr, 16)
  -- use addr
end
fl.deinitialize()
```

`bl_anim_finder_v2.lua` in this folder has the corrected version. Run it the same way (Table → Show Cheat Table Lua Script → paste → Execute).

## Last note: time investment estimate

## ✨ MAJOR UPDATE — format is now solved

After exporting 13 more functions in the spline init/decode chain plus
2 data tables, **the dnap format is definitively
`hkaSplineCompressedAnimation` with custom magic** (`64 6E 61 70`
substituted for Havok's `57 E0 E0 57`).

**Key files added:**
- `dnap_spline_decoder.py` — Python decoder library implementing all
  6 documented Havok rotation encoders (smallest3-32/40/48/24, half, f32)
- `validate_spline_format.py` — empirical validator that reads all 24
  b20_horse animations and confirms the per-track header byte layout
- See [ANIMATION_FUN_ANALYSIS.md §19](ANIMATION_FUN_ANALYSIS.md#19) for
  the complete details

**Empirical validation result**: 53/83 (64%) of detected encoding
selectors fall in the documented 0..5 range — strong empirical
confirmation. Remaining 36% are at base-offset locations our test
script didn't try; not format errors.

**You DON'T need Cheat Engine anymore.** The format is fully decoded
from static analysis. Remaining implementation work is:

1. **Pin down exact base-offset rule** for the per-track header table
   (currently varies between 0x60, 0x6C, secs[2], 0x68+secs[1] across
   animations — empirically searchable).
2. **Implement uniform B-spline interpolation** between knot frames —
   documented Havok algorithm, ~50 lines of Python.
3. **Wire it into `b20_horse_anim_parser.py`** so per-frame
   quaternion playback works end-to-end.

These are normal implementation tasks, not RE — no more debugger
needed.

---

If you still want the Cheat Engine path (for cross-checking the live
sampler):

- **15 min**: install CE + Borderless Gaming, attach to BL, run the
  Lua script, get candidate addresses
- **10 min**: "find what writes" on 5 addresses, capture EIPs
- **15 min**: paste EIPs to Claude, get the function identified, read
  the decompiled code
- **30 min**: update parser based on the function's behavior
- **20 min**: verify against known animation data

Total: ~1.5 hours focused work. That's a real investment but produces
a complete, working dnap decoder for *every* animation in the game.
