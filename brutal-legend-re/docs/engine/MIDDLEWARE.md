# Middleware Documentation

**Status:** In Progress  
**Game:** Brutal Legend  

---

## Confirmed Middleware

### FMOD (Audio)
- FSB sound banks
- Custom encryption
- See [AUDIO_SPEC.md](../formats/AUDIO_SPEC.md)

### ZLib (Compression)
- Standard DEFLATE compression
- Used in DFPF containers and UI .gfx files

### Scaleform GFx (CONFIRMED)
- UI middleware: Scaleform GFx 3.x
- Binary header analysis: 47 46 58 08 (GFX signature, version 3.x)
- ZLib compressed .gfx files
- See [UI_FORMAT.md](../formats/UI_FORMAT.md)

### Havok Physics
- Expected for 2009 era games
- Havok-6.1.0-r1

### Havok Animations
- using custom wrapper (.AnimResource, .AnimResource.header)
- version unconfirmed
- possibly uses Gzip/ZLib Compression
- [ANIM_FORMAT.md](../formats/ANIM_FORMAT.md)

### Havok Versions found
- Havok-3.1.0	
- Havok-3.0.0	
- Havok-5.0.0-b1	
- Havok-5.0.0-r1	
- Havok-5.1.0-r1	
- Havok-4.0.0-b1	

## Unconfirmed Middleware

### Bink Video
- Cutscene codec
- Needs verification

---

## TODO

Verify Havok and Bink via dumpbin /imports on BrutalLegend.exe
