# Brutal Legend dnap runtime debugging — step-by-step

Goal: capture the **live sampler function address** by setting a memory
breakpoint inside an in-memory dnap buffer and reading the call stack
when the engine reads from it.

## Tooling

You'll need:
- **x32dbg** (https://x64dbg.com/) — free, x86 mode for the 32-bit BL.exe
- A save where the **horse is on screen and animating** (any Reaper section)

## Procedure

### 1. Launch with debugger attached

Easiest: open `BrutalLegend.exe` in x32dbg via *File → Open*. Run
until the game window shows the horse (it pauses at the entry point;
press F9 / "Run" twice to skip the typical CRT init breakpoints).

### 2. Find the dnap buffers in memory

Once the horse is visible:

a. **Pause** the game (`F12` in x32dbg).
b. Open *Search → Memory pattern → in current module*.
c. Search across **all** memory (not just .exe), because the dnap
   buffer is heap-allocated.
d. **Pattern**: `64 6E 61 70` (= "dnap" little-endian, 4 bytes)
e. You should get **~27 hits** — one per loaded b20_horse animation.

Actually, the game probably keeps **multiple animation instances** per
clip (one per active blend channel), so you may see more than 27. Pick
any.

### 3. Prefer `relaxed_breathe` (smallest, easiest to inspect)

Right-click each hit → *Follow in Dump*. Look at the bytes at
`+0x04..+0x0B`:

- `relaxed_breathe`: `CC CC CC 3F` (period=1.6) + `?? ?? F0 41` (fps=30)
- `relaxed_trot`:    `56 55 55 3F` (period=0.833)
- `sleep_breathe`:   `00 00 80 40` (period=4.0)

Pick the breathe instance — it's only 1120 bytes total so any
breakpoint will fire predictably.

### 4. Set a hardware READ breakpoint

In the dump view, scroll to `+0x40` (the section size table). Right-click
the byte at offset `0x40` from the dnap base → **Hardware breakpoint →
Read** (size=byte or dword, your choice; dword recommended).

### 5. Resume

Press `F9` to resume. **The breakpoint will hit within ~1 frame** (60
times per second the engine reads this).

### 6. Capture the call stack

When it breaks:
- The current function is the **innermost reader**.
- Open the *Call Stack* pane (typically docked at bottom right).
- Note the **top 4-5 frames** — addresses + module offsets.

The pattern you're looking for:
- Frame 0: low-level read (probably small leaf function)
- Frame 1-2: per-track loop (likely calls FUN_00dd7b00-equivalent)
- Frame 3-4: **per-frame sample dispatch** ← this is the function we want
- Frame 5+: CoSkeleton / animator update / game tick

Save the call-stack as a text dump (right-click stack → *Copy →
Selection*).

### 7. What to do with the addresses

Send me the call-stack output. With the live-sampler function's address,
I can:
1. Decompile it in Ghidra via the MCP connection.
2. Reverse-engineer its byte-fetch pattern (which file offsets it reads).
3. Update `b20_horse_anim_parser.py` with the actual format.

## Common pitfalls

- **Memory protection**: if x32dbg complains about hardware breakpoint
  failing, use a **memory access breakpoint** instead (Memory →
  Memory access). Slightly slower but works on any address.
- **Optimized hot paths**: the live sampler may have its prologue
  inlined. If frame 0 looks like a small "JMP back" stub, frame 1 is
  the real function.
- **Multiple consumers**: bone-update vs. event-firing might both read
  dnap. Set the BP at `+0x40` (rare-read) rather than `+0x10`
  (frequent-read) to maximize signal-to-noise.
- **Wrong instance**: if the breakpoint never fires, you may have
  picked an instance that's loaded but not currently sampling.
  Switch to a different match.
