#!/usr/bin/env python3
"""
Brutal Legend Terrain Editor
============================
A tool for editing terrain data for Brutal Legend maps.

Supports TWO formats:
1. DDS Heightfield (.Heightfield) - DXT5 compressed texture with 40-byte custom header
2. MeshSet Terrain Tile (height.bin) - "hsem" magic format for terrain tiles

Commands:
  view        - Display terrain data as text summary
  edit-height - Raise/lower terrain in a region by a delta value
  smooth      - Apply box blur to terrain region
  export-image - Export as PNG visualization
  create      - Generate a minimal test terrain tile
"""

import struct
import sys
import os
import argparse
from typing import Optional, Tuple, List, Union
from abc import ABC, abstractmethod

# Optional: Pillow for image export
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("Warning: Pillow not installed. Image export disabled.")

# Optional: numpy for numerical operations
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    print("Warning: numpy not installed. Using pure Python (slower).")


# Constants for DDS format
DDS_MAGIC = 0x20534444  # 'DDS '
DXT5_BLOCK_SIZE = 16  # 4x4 pixels per block
CUSTOM_HEADER_SIZE = 40
DDS_HEADER_SIZE = 124

# Constants for MeshSet format
HSEM_MAGIC = b'hsem'
LRTM_MAGIC = b'lrtm'
BVXD_MAGIC = b'BVXD'
BIXD_MAGIC = b'BIXD'


# =============================================================================
# DDS Format Support
# =============================================================================

class HeightfieldHeader:
    """Custom 40-byte header for Brutal Legend Heightfield DDS files."""

    def __init__(self):
        self.metadata = bytes(8)
        self.type_marker = 0x0b
        self.unknown_0c = bytes(4)
        self.width_hint = 128
        self.height_hint = 128
        self.unknown_18 = bytes(8)
        self.texture_marker = 0x54787274  # 'rtxT'
        self.data_size = 0

    @staticmethod
    def parse(data: bytes) -> 'HeightfieldHeader':
        """Parse header from 40-byte buffer."""
        if len(data) < 40:
            raise ValueError(f"Header too short: {len(data)} bytes, need 40")

        hdr = HeightfieldHeader()
        hdr.metadata = data[0x00:0x08]
        hdr.type_marker = struct.unpack('<I', data[0x08:0x0C])[0]
        hdr.unknown_0c = data[0x0C:0x10]
        hdr.width_hint = struct.unpack('<I', data[0x10:0x14])[0]
        hdr.height_hint = struct.unpack('<I', data[0x14:0x18])[0]
        hdr.unknown_18 = data[0x18:0x20]
        hdr.texture_marker = struct.unpack('<I', data[0x20:0x24])[0]
        hdr.data_size = struct.unpack('<I', data[0x24:0x28])[0]
        return hdr

    def to_bytes(self) -> bytes:
        """Serialize header to 40 bytes."""
        out = bytearray(40)
        out[0x00:0x08] = self.metadata
        out[0x08:0x0C] = struct.pack('<I', self.type_marker)
        out[0x0C:0x10] = self.unknown_0c
        out[0x10:0x14] = struct.pack('<I', self.width_hint)
        out[0x14:0x18] = struct.pack('<I', self.height_hint)
        out[0x18:0x20] = self.unknown_18
        out[0x20:0x24] = struct.pack('<I', self.texture_marker)
        out[0x24:0x28] = struct.pack('<I', self.data_size)
        return bytes(out)

    def validate(self) -> bool:
        """Check header fields are valid for a heightfield DDS."""
        valid = True
        if self.type_marker != 0x0b:
            print(f"Warning: type_marker is 0x{self.type_marker:02X}, expected 0x0B")
            valid = False
        if self.texture_marker != 0x54787274:
            print(f"Warning: texture_marker is 0x{self.texture_marker:08X}, expected 0x54787274 ('rtxT')")
            valid = False
        return valid


def decode_dxt5_block(block: bytes) -> List[int]:
    """
    Decode DXT5 block (16 bytes) to 16 alpha values.
    DXT5 stores color in R5G6B5 and uses alpha channel for height.
    Returns list of 16 alpha values (0-255).
    """
    if len(block) < 16:
        raise ValueError(f"Block too short: {len(block)} bytes")

    alpha0 = block[0]
    alpha1 = block[1]

    # Build alpha interpolation table
    if alpha0 > alpha1:
        alpha_table = [
            alpha0,
            alpha1,
            (6*alpha0 + 1*alpha1) // 7,
            (5*alpha0 + 2*alpha1) // 7,
            (4*alpha0 + 3*alpha1) // 7,
            (3*alpha0 + 4*alpha1) // 7,
            (2*alpha0 + 5*alpha1) // 7,
            (1*alpha0 + 6*alpha1) // 7,
        ]
    else:
        alpha_table = [
            alpha0,
            alpha1,
            (4*alpha0 + 1*alpha1) // 5,
            (3*alpha0 + 2*alpha1) // 5,
            (2*alpha0 + 3*alpha1) // 5,
            (1*alpha0 + 4*alpha1) // 5,
            0,
            255,
        ]

    # Decode alpha indices (3 bits per pixel, 16 pixels)
    alpha_bits = struct.unpack('<Q', block[0:8])[0]
    alphas = []
    for i in range(16):
        idx = (alpha_bits >> (3 * i)) & 0x07
        alphas.append(alpha_table[idx])

    return alphas


def encode_dxt5_block(alphas: List[int]) -> bytes:
    """
    Encode 16 alpha values into a DXT5 block (16 bytes).
    Uses simple endpoint encoding.
    """
    if len(alphas) != 16:
        raise ValueError(f"Expected 16 alphas, got {len(alphas)}")

    # Find min/max alpha values as endpoints
    alpha0 = max(alphas)
    alpha1 = min(alphas)

    # Build interpolation table
    if alpha0 > alpha1:
        alpha_table = [
            alpha0,
            alpha1,
            (6*alpha0 + 1*alpha1) // 7,
            (5*alpha0 + 2*alpha1) // 7,
            (4*alpha0 + 3*alpha1) // 7,
            (3*alpha0 + 4*alpha1) // 7,
            (2*alpha0 + 5*alpha1) // 7,
            (1*alpha0 + 6*alpha1) // 7,
        ]
    else:
        alpha_table = [
            alpha0,
            alpha1,
            (4*alpha0 + 1*alpha1) // 5,
            (3*alpha0 + 2*alpha1) // 5,
            (2*alpha0 + 3*alpha1) // 5,
            (1*alpha0 + 4*alpha1) // 5,
            0,
            255,
        ]

    # Encode alpha indices
    alpha_bits = 0
    for i, a in enumerate(alphas):
        if a == alpha0:
            idx = 0
        elif a == alpha1:
            idx = 1
        else:
            best_dist = 256
            best_idx = 2
            for j in range(2, 8):
                dist = abs(a - alpha_table[j])
                if dist < best_dist:
                    best_dist = dist
                    best_idx = j
            idx = best_idx
        alpha_bits |= (idx << (3 * i))

    # Color endpoints (placeholder - use first pixel's color)
    color0 = 0xFFFF  # R5G6B5 white
    color1 = 0x0000  # R5G6B5 black

    # Color indices (all same color for heightfield)
    color_bits = 0x55555555  # All index 1

    out = bytearray(16)
    struct.pack_into('<Q', out, 0, alpha_bits)
    struct.pack_into('<H', out, 8, color0)
    struct.pack_into('<H', out, 10, color1)
    struct.pack_into('<I', out, 12, color_bits)
    return bytes(out)


def decode_dxt5_texture(width: int, height: int, data: bytes) -> List[List[int]]:
    """
    Decode DXT5 texture to 2D heightmap (alpha channel as height).
    Returns heightmap as list of lists of integers (0-255).
    """
    blocks_x = (width + 3) // 4
    blocks_y = (height + 3) // 4

    heightmap = [[0] * width for _ in range(height)]

    for by in range(blocks_y):
        for bx in range(blocks_x):
            block_offset = (by * blocks_x + bx) * DXT5_BLOCK_SIZE
            if block_offset + DXT5_BLOCK_SIZE > len(data):
                break

            block = data[block_offset:block_offset + DXT5_BLOCK_SIZE]
            alphas = decode_dxt5_block(block)

            # Place 4x4 block into heightmap
            start_x = bx * 4
            start_y = by * 4
            for py in range(4):
                for px in range(4):
                    x = start_x + px
                    y = start_y + py
                    if x < width and y < height:
                        heightmap[y][x] = alphas[py * 4 + px]

    return heightmap


def encode_dxt5_texture(width: int, height: int, heightmap: List[List[int]]) -> bytes:
    """
    Encode heightmap into DXT5 texture.
    Takes 2D heightmap (list of lists of 0-255) and returns compressed DXT5 bytes.
    """
    blocks_x = (width + 3) // 4
    blocks_y = (height + 3) // 4

    output = bytearray()
    for by in range(blocks_y):
        for bx in range(blocks_x):
            # Extract 4x4 block alphas
            alphas = []
            for py in range(4):
                for px in range(4):
                    x = bx * 4 + px
                    y = by * 4 + py
                    if x < width and y < height:
                        alphas.append(heightmap[y][x])
                    else:
                        alphas.append(0)

            block = encode_dxt5_block(alphas)
            output.extend(block)

    return bytes(output)


class DDSHeightfield:
    """
    Represents a Brutal Legend Heightfield DDS file.

    File structure:
    - 0x00-0x27: 40-byte custom header
    - 0x28-0x2B: 'DDS ' magic
    - 0x2C-0xA7: 124-byte DDS header
    - 0xA8+: DXT5 compressed data
    """

    DDS_OFFSET = 0x28
    DDS_HEADER_OFFSET = 0x2C  # DDS header starts after custom header + 'DDS ' magic
    DATA_OFFSET = 0xA8

    def __init__(self):
        self.custom_header = HeightfieldHeader()
        self.width = 128
        self.height = 128
        self.dxt5_data = b''
        self.extra_data = b''
        self.heightmap: List[List[int]] = []

    @classmethod
    def load(cls, filepath: str) -> 'DDSHeightfield':
        """Load a heightfield DDS file."""
        hf = cls()

        try:
            with open(filepath, 'rb') as f:
                data = f.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"Heightfield file not found: {filepath}")
        except IOError as e:
            raise IOError(f"Error reading heightfield: {e}")

        if len(data) < 0xA8:
            raise ValueError(f"File too small: {len(data)} bytes (expected at least 168)")

        # Parse custom header
        hf.custom_header = HeightfieldHeader.parse(data[0:CUSTOM_HEADER_SIZE])

        # Verify DDS magic
        dds_magic = struct.unpack('<I', data[0x28:0x2C])[0]
        if dds_magic != DDS_MAGIC:
            raise ValueError(f"Invalid DDS magic: 0x{dds_magic:08X}, expected 0x{DDS_MAGIC:08X} ('DDS ')")

        # Parse DDS header to get dimensions
        # DDS header starts at DDS_HEADER_OFFSET (0x2C)
        # Pixel format (PIXELFORMAT) starts at offset 0x50 within DDS header
        dds_flags = struct.unpack('<I', data[cls.DDS_HEADER_OFFSET + 0x04:cls.DDS_HEADER_OFFSET + 0x08])[0]
        dds_height = struct.unpack('<I', data[cls.DDS_HEADER_OFFSET + 0x08:cls.DDS_HEADER_OFFSET + 0x0C])[0]
        dds_width = struct.unpack('<I', data[cls.DDS_HEADER_OFFSET + 0x0C:cls.DDS_HEADER_OFFSET + 0x10])[0]
        pf_flags = struct.unpack('<I', data[cls.DDS_HEADER_OFFSET + 0x54:cls.DDS_HEADER_OFFSET + 0x58])[0]
        pf_fourcc = struct.unpack('<I', data[cls.DDS_HEADER_OFFSET + 0x58:cls.DDS_HEADER_OFFSET + 0x5C])[0]

        # Check for DXT5 format
        if pf_fourcc != 0x35545844:  # 'DXT5'
            raise ValueError(f"Only DXT5 format supported, got: 0x{pf_fourcc:08X}")

        hf.width = dds_width
        hf.height = dds_height

        # Calculate expected DXT5 data size
        blocks_x = (hf.width + 3) // 4
        blocks_y = (hf.height + 3) // 4
        expected_dxt5_size = blocks_x * blocks_y * DXT5_BLOCK_SIZE

        # Extract DXT5 data (use header data_size if available)
        if hf.custom_header.data_size > 0:
            dxt5_size = min(hf.custom_header.data_size, len(data) - cls.DATA_OFFSET)
        else:
            dxt5_size = min(expected_dxt5_size, len(data) - cls.DATA_OFFSET)

        hf.dxt5_data = data[cls.DATA_OFFSET:cls.DATA_OFFSET + dxt5_size]

        # Extra data after DXT5
        extra_offset = cls.DATA_OFFSET + len(hf.dxt5_data)
        if extra_offset < len(data):
            hf.extra_data = data[extra_offset:]

        # Decode heightmap
        hf.heightmap = decode_dxt5_texture(hf.width, hf.height, hf.dxt5_data)

        return hf

    def save(self, filepath: str):
        """Save heightfield to DDS file."""
        # Encode heightmap to DXT5
        self.dxt5_data = encode_dxt5_texture(self.width, self.height, self.heightmap)
        self.custom_header.data_size = len(self.dxt5_data)
        self.custom_header.width_hint = self.width
        self.custom_header.height_hint = self.height

        try:
            with open(filepath, 'wb') as f:
                # Write custom header (40 bytes)
                f.write(self.custom_header.to_bytes())

                # Write 'DDS ' magic
                f.write(b'DDS ')

                # Write DDS header (124 bytes)
                dds_header = bytearray(124)
                struct.pack_into('<I', dds_header, 0, 124)  # dwSize
                struct.pack_into('<I', dds_header, 4, 0x21007)  # dwFlags
                struct.pack_into('<I', dds_header, 8, self.height)  # dwHeight
                struct.pack_into('<I', dds_header, 12, self.width)  # dwWidth
                struct.pack_into('<I', dds_header, 16, 0)  # dwPitchOrLinearSize
                struct.pack_into('<I', dds_header, 20, 0)  # dwDepth
                struct.pack_into('<I', dds_header, 24, 1)  # dwMipMapCount
                # reserved1 (44 bytes of zeros) at offset 28
                # Pixel format (PIXELFORMAT) starts at offset 0x50 within DDS header
                struct.pack_into('<I', dds_header, 0x50, 32)  # pf.dwSize
                struct.pack_into('<I', dds_header, 0x54, 0x04 | 0x40000)  # pf.dwFlags (FOURCC)
                struct.pack_into('<I', dds_header, 0x58, 0x35545844)  # pf.dwFourCC ('DXT5')
                struct.pack_into('<I', dds_header, 0x5C, 0)  # pf.dwRGBBitCount
                struct.pack_into('<I', dds_header, 0x60, 0)  # pf.dwRBitMask
                struct.pack_into('<I', dds_header, 0x64, 0)  # pf.dwGBitMask
                struct.pack_into('<I', dds_header, 0x68, 0)  # pf.dwBBitMask
                struct.pack_into('<I', dds_header, 0x6C, 0xFF)  # pf.dwABitMask
                struct.pack_into('<I', dds_header, 0x6C + 4, 0x1000 | 0x04)  # dwCaps (COMPLEX | TEXTURE)
                struct.pack_into('<I', dds_header, 112, 0)  # dwCaps2
                struct.pack_into('<I', dds_header, 116, 0)  # dwCaps3
                struct.pack_into('<I', dds_header, 120, 0)  # dwCaps4
                f.write(dds_header)

                # Write DXT5 data
                f.write(self.dxt5_data)

                # Write extra data
                if self.extra_data:
                    f.write(self.extra_data)

        except IOError as e:
            raise IOError(f"Error saving heightfield: {e}")

    def get_stats(self) -> dict:
        """Calculate heightfield statistics."""
        if not self.heightmap:
            return {'min': 0, 'max': 0, 'avg': 0, 'width': self.width, 'height': self.height}

        min_h = 255
        max_h = 0
        total = 0
        count = 0

        for row in self.heightmap:
            for h in row:
                if h > 0:
                    min_h = min(min_h, h)
                    max_h = max(max_h, h)
                    total += h
                    count += 1

        if count == 0:
            return {'min': 0, 'max': 0, 'avg': 0, 'width': self.width, 'height': self.height}

        return {
            'min': min_h,
            'max': max_h,
            'avg': total / count,
            'width': self.width,
            'height': self.height
        }

    def edit_height_region(self, x1: int, y1: int, x2: int, y2: int, delta: int):
        """Raise or lower terrain in a rectangular region."""
        x1 = max(0, min(x1, self.width))
        y1 = max(0, min(y1, self.height))
        x2 = max(0, min(x2, self.width))
        y2 = max(0, min(y2, self.height))

        if x1 >= x2 or y1 >= y2:
            print(f"Warning: Invalid region ({x1},{y1})-({x2},{y2}), skipping")
            return

        print(f"Editing region: ({x1},{y1}) to ({x2},{y2}), delta={delta}")

        for y in range(y1, y2):
            for x in range(x1, x2):
                new_h = self.heightmap[y][x] + delta
                self.heightmap[y][x] = max(0, min(255, new_h))

    def smooth_region(self, x1: int, y1: int, x2: int, y2: int, iterations: int = 1):
        """Apply box blur to a rectangular region."""
        x1 = max(0, min(x1, self.width))
        y1 = max(0, min(y1, self.height))
        x2 = max(0, min(x2, self.width))
        y2 = max(0, min(y2, self.height))

        if x1 >= x2 or y1 >= y2:
            print(f"Warning: Invalid region ({x1},{y1})-({x2},{y2}), skipping")
            return

        print(f"Smoothing region: ({x1},{y1}) to ({x2},{y2}), iterations={iterations}")

        for _ in range(iterations):
            smoothed = [row[:] for row in self.heightmap]

            for y in range(y1, y2):
                for x in range(x1, x2):
                    sum_h = 0
                    count = 0
                    for ny in range(max(0, y-1), min(self.height, y+2)):
                        for nx in range(max(0, x-1), min(self.width, x+2)):
                            sum_h += self.heightmap[ny][nx]
                            count += 1
                    smoothed[y][x] = sum_h // count

            self.heightmap = smoothed

    def export_image(self, filepath: str):
        """Export heightfield as grayscale PNG image."""
        if not HAS_PIL:
            raise ImportError("Pillow not installed, cannot export image")

        stats = self.get_stats()
        img_data = []
        for y in range(self.height):
            row = []
            for x in range(self.width):
                h = self.heightmap[y][x]
                if stats['max'] > stats['min']:
                    normalized = int((h - stats['min']) / (stats['max'] - stats['min']) * 255)
                else:
                    normalized = h
                row.append(normalized)
            img_data.append(row)

        img = Image.new('L', (self.width, self.height))
        for y in range(self.height):
            for x in range(self.width):
                img.putpixel((x, y), img_data[y][x])

        img.save(filepath, 'PNG')
        print(f"Exported heightfield to {filepath}")


# =============================================================================
# MeshSet Format Support (height.bin terrain tiles)
# =============================================================================

class MeshSetTerrain:
    """
    Represents a MeshSet terrain tile (height.bin) file.

    File structure:
    - 0x00-0x03: "hsem" magic (reversed "mesh")
    - 0x04-0x0B: Unknown
    - 0x0C-0x13: Two floats (scale values)
    - 0x14-0x1F: More floats (possibly height range)
    - 0x20-0x23: "lrtm" magic (terrain marker)
    - 0x24-0x27: Version (0x01000000)
    - 0x28-0x2B: Count
    - 0x2C+: Strings and metadata
    - Data section: uint16 indices in range 0x0400-0x04FF

    The height data appears to be stored as material layer indices.
    """

    def __init__(self):
        self.magic = HSEM_MAGIC
        self.unknown_04 = bytes(8)
        self.scale_x = 1.0
        self.scale_y = 1.0
        self.range_min = 0.0
        self.range_max = 0.0
        self.unknown_18 = bytes(8)
        self.lrtm_marker = LRTM_MAGIC
        self.version = 0x01000000
        self.count = 0
        self.material_path = ""
        self.format_marker1 = BVXD_MAGIC
        self.unknown_74 = bytes(4)
        self.format_marker2 = BIXD_MAGIC
        # Height data as 2D grid of indices (stored as actual height values for editing)
        self.width = 0
        self.height = 0
        self.height_data: List[List[int]] = []
        self.extra_data = b''

    @classmethod
    def load(cls, filepath: str) -> 'MeshSetTerrain':
        """Load a MeshSet terrain tile file."""
        tile = cls()

        try:
            with open(filepath, 'rb') as f:
                data = f.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"Terrain tile file not found: {filepath}")
        except IOError as e:
            raise IOError(f"Error reading terrain tile: {e}")

        if len(data) < 0x80:
            raise ValueError(f"File too small: {len(data)} bytes (expected at least 128)")

        # Verify "hsem" magic
        if data[0:4] != HSEM_MAGIC:
            raise ValueError(f"Invalid magic: {data[0:4]!r}, expected {HSEM_MAGIC!r}")

        tile.unknown_04 = data[0x04:0x0C]

        # Scale values at 0x0C
        tile.scale_x, tile.scale_y = struct.unpack('<ff', data[0x0C:0x14])

        # Range values at 0x14
        tile.range_min, tile.range_max = struct.unpack('<ff', data[0x14:0x1C])

        tile.unknown_18 = data[0x1C:0x24]

        # "lrtm" at 0x20
        tile.lrtm_marker = data[0x20:0x24]
        if tile.lrtm_marker != LRTM_MAGIC:
            print(f"Warning: 'lrtm' marker not found at 0x20, got {tile.lrtm_marker!r}")

        # Version at 0x24
        tile.version = struct.unpack('<I', data[0x24:0x28])[0]

        # Count at 0x28
        tile.count = struct.unpack('<I', data[0x28:0x2C])[0]

        # Material path string (null-terminated, starting at 0x2C)
        null_pos = data.find(b'\x00', 0x2C)
        if null_pos > 0:
            tile.material_path = data[0x2C:null_pos].decode('ascii', errors='replace')
        else:
            tile.material_path = ""

        # Find "BVXD" marker (should be at 0x70 based on spec)
        bvxd_pos = data.find(BVXD_MAGIC, 0x30)
        if bvxd_pos < 0:
            print("Warning: 'BVXD' marker not found")

        # Find "BIXD" marker after BVXD
        bixd_pos = data.find(BIXD_MAGIC, bvxd_pos + 4 if bvxd_pos >= 0 else 0x70)
        if bixd_pos < 0:
            print("Warning: 'BIXD' marker not found")

        # Extract format markers
        if bvxd_pos >= 0:
            tile.format_marker1 = data[bvxd_pos:bvxd_pos+4]
        if bixd_pos >= 0:
            tile.format_marker2 = data[bixd_pos:bixd_pos+4]

        # Calculate height data dimensions
        # The data section starts after headers and contains uint16 indices
        # Based on spec, indices are in range 0x0400-0x04FF (1024-1279)
        # These represent material layer indices

        # Find where the actual data starts
        # After BIXD marker, there may be additional header info before data
        data_start = bixd_pos + 4 if bixd_pos >= 0 else 0x80

        # Align to 4-byte boundary
        while data_start % 4 != 0:
            data_start += 1

        # Read remaining data as uint16 indices
        remaining = data[data_start:]

        # Determine grid size - try to find a reasonable dimension
        # The data appears to be a 2D grid, likely 46x46 or similar based on count
        # Use the count value as hint for grid dimensions
        if tile.count > 0:
            # Estimate grid size from count
            grid_dim = int((tile.count ** 0.5)) + 1
            # Ensure we have a reasonable size
            grid_dim = max(16, min(grid_dim, 256))
        else:
            grid_dim = 46  # Default based on spec (0x2e = 46)

        # Actually, let's calculate from remaining data size
        num_elements = len(remaining) // 2  # Each element is 2 bytes (uint16)

        # Find best fit for grid dimensions (they should be similar)
        best_dim = int(num_elements ** 0.5)
        for dim in range(best_dim, best_dim + 4):
            if dim * dim <= num_elements:
                tile.height = dim
                tile.width = dim
                break

        # Initialize height data grid from indices
        # Map the uint16 indices (0x0400-0x04FF) to height values (0-255)
        tile.height_data = [[0] * tile.width for _ in range(tile.height)]

        idx = 0
        for y in range(tile.height):
            for x in range(tile.width):
                if idx * 2 + 1 < len(remaining):
                    val = struct.unpack('<H', remaining[idx*2:idx*2+2])[0]
                    # Map from 0x0400-0x04FF range (1024-1279) to 0-255
                    # Normalize: subtract 0x0400 and scale
                    if 0x0400 <= val <= 0x04FF:
                        mapped = ((val - 0x0400) * 255) // 0xFF
                    else:
                        # Use raw mapping for any other values
                        mapped = (val * 255) // 0xFFFF
                    tile.height_data[y][x] = min(255, mapped)
                idx += 1

        # Store any extra data after the height data
        extra_start = idx * 2
        if extra_start < len(remaining):
            tile.extra_data = remaining[extra_start:]

        return tile

    def save(self, filepath: str):
        """Save MeshSet terrain tile to file."""
        # Calculate height data size
        grid_size = self.width * self.height

        # Build header
        header = bytearray(0x80)  # Minimum header size

        # "hsem" magic at 0x00
        header[0x00:0x04] = HSEM_MAGIC

        # Unknown at 0x04
        header[0x04:0x0C] = self.unknown_04

        # Scale values at 0x0C
        struct.pack_into('<ff', header, 0x0C, self.scale_x, self.scale_y)

        # Range values at 0x14
        struct.pack_into('<ff', header, 0x14, self.range_min, self.range_max)

        # Unknown at 0x1C
        header[0x1C:0x24] = self.unknown_18

        # "lrtm" at 0x20
        header[0x20:0x24] = LRTM_MAGIC

        # Version at 0x24
        struct.pack_into('<I', header, 0x24, self.version)

        # Count at 0x28
        struct.pack_into('<I', header, 0x28, grid_size)

        # Material path at 0x2C (null-terminated)
        if self.material_path:
            path_bytes = self.material_path.encode('ascii') + b'\x00'
            header[0x2C:0x2C+len(path_bytes)] = path_bytes

        # "BVXD" at 0x70
        header[0x70:0x74] = BVXD_MAGIC

        # Unknown at 0x74
        header[0x74:0x78] = bytes([0x02, 0x00, 0x00, 0x00])

        # Unknown at 0x78
        header[0x78:0x7C] = bytes([0x00, 0x00, 0x00, 0x00])

        # "BIXD" at 0x7C
        header[0x7C:0x80] = BIXD_MAGIC

        # Build height data (convert height values back to uint16 indices)
        data_section = bytearray()
        for y in range(self.height):
            for x in range(self.width):
                h = self.height_data[y][x]
                # Map from 0-255 to 0x0400-0x04FF range
                val = 0x0400 + (h * 0xFF) // 255
                # Clamp to valid range
                val = max(0x0400, min(0x04FF, val))
                data_section.extend(struct.pack('<H', val))

        # Write file
        try:
            with open(filepath, 'wb') as f:
                f.write(header)
                f.write(data_section)
                if self.extra_data:
                    f.write(self.extra_data)
        except IOError as e:
            raise IOError(f"Error saving terrain tile: {e}")

    def get_stats(self) -> dict:
        """Calculate terrain tile statistics."""
        if not self.height_data:
            return {'min': 0, 'max': 0, 'avg': 0, 'width': self.width, 'height': self.height}

        min_h = 255
        max_h = 0
        total = 0
        count = 0

        for row in self.height_data:
            for h in row:
                if h > 0:
                    min_h = min(min_h, h)
                    max_h = max(max_h, h)
                    total += h
                    count += 1

        if count == 0:
            return {'min': 0, 'max': 0, 'avg': 0, 'width': self.width, 'height': self.height}

        return {
            'min': min_h,
            'max': max_h,
            'avg': total / count,
            'width': self.width,
            'height': self.height
        }

    def edit_height_region(self, x1: int, y1: int, x2: int, y2: int, delta: int):
        """Raise or lower terrain in a rectangular region."""
        x1 = max(0, min(x1, self.width))
        y1 = max(0, min(y1, self.height))
        x2 = max(0, min(x2, self.width))
        y2 = max(0, min(y2, self.height))

        if x1 >= x2 or y1 >= y2:
            print(f"Warning: Invalid region ({x1},{y1})-({x2},{y2}), skipping")
            return

        print(f"Editing region: ({x1},{y1}) to ({x2},{y2}), delta={delta}")

        for y in range(y1, y2):
            for x in range(x1, x2):
                new_h = self.height_data[y][x] + delta
                self.height_data[y][x] = max(0, min(255, new_h))

    def smooth_region(self, x1: int, y1: int, x2: int, y2: int, iterations: int = 1):
        """Apply box blur to a rectangular region."""
        x1 = max(0, min(x1, self.width))
        y1 = max(0, min(y1, self.height))
        x2 = max(0, min(x2, self.width))
        y2 = max(0, min(y2, self.height))

        if x1 >= x2 or y1 >= y2:
            print(f"Warning: Invalid region ({x1},{y1})-({x2},{y2}), skipping")
            return

        print(f"Smoothing region: ({x1},{y1}) to ({x2},{y2}), iterations={iterations}")

        for _ in range(iterations):
            smoothed = [row[:] for row in self.height_data]

            for y in range(y1, y2):
                for x in range(x1, x2):
                    sum_h = 0
                    count = 0
                    for ny in range(max(0, y-1), min(self.height, y+2)):
                        for nx in range(max(0, x-1), min(self.width, x+2)):
                            sum_h += self.height_data[ny][nx]
                            count += 1
                    smoothed[y][x] = sum_h // count

            self.height_data = smoothed

    def export_image(self, filepath: str):
        """Export terrain as grayscale PNG image."""
        if not HAS_PIL:
            raise ImportError("Pillow not installed, cannot export image")

        stats = self.get_stats()

        img = Image.new('L', (self.width, self.height))
        for y in range(self.height):
            for x in range(self.width):
                h = self.height_data[y][x]
                if stats['max'] > stats['min']:
                    normalized = int((h - stats['min']) / (stats['max'] - stats['min']) * 255)
                else:
                    normalized = h
                img.putpixel((x, y), normalized)

        img.save(filepath, 'PNG')
        print(f"Exported terrain to {filepath}")


# =============================================================================
# Format Detection and Unified Interface
# =============================================================================

def detect_format(filepath: str) -> str:
    """
    Detect the format of a terrain file.
    Returns 'dds', 'meshset', or 'unknown'.
    """
    try:
        with open(filepath, 'rb') as f:
            header = f.read(0x30)  # Read enough for all headers

        if len(header) < 4:
            return 'unknown'

        # Check for MeshSet "hsem" magic at start
        if header[0:4] == HSEM_MAGIC:
            return 'meshset'

        # Check for DDS "DDS " magic at offset 0x28
        if header[0x28:0x2C] == b'DDS ':
            return 'dds'

        # Check for DDS "DDS " magic at start (some DDS files may start this way)
        if header[0:4] == b'DDS ':
            return 'dds'

        # Check for custom header with 'rtxT' marker at 0x20
        if len(header) >= 0x24:
            texture_marker = struct.unpack('<I', header[0x20:0x24])[0]
            if texture_marker == 0x72747854:  # 'rtxT' (little-endian)
                return 'dds'

        return 'unknown'

    except Exception:
        return 'unknown'


def load_terrain(filepath: str) -> Union[DDSHeightfield, MeshSetTerrain]:
    """
    Load a terrain file, auto-detecting the format.
    Returns either DDSHeightfield or MeshSetTerrain.
    """
    fmt = detect_format(filepath)

    if fmt == 'dds':
        return DDSHeightfield.load(filepath)
    elif fmt == 'meshset':
        return MeshSetTerrain.load(filepath)
    else:
        raise ValueError(f"Unknown terrain format for file: {filepath}")


def validate_input_file(filepath: str) -> bool:
    """Check if file exists and appears to be a valid terrain file."""
    if not os.path.exists(filepath):
        print(f"Error: File not found: {filepath}")
        return False

    fmt = detect_format(filepath)
    if fmt == 'unknown':
        print(f"Warning: Cannot detect terrain format for: {filepath}")
        return False

    return True


# =============================================================================
# Commands
# =============================================================================

def cmd_view(args):
    """Display terrain data as text summary."""
    if not validate_input_file(args.input):
        return 1

    fmt = detect_format(args.input)
    print(f"\nLoading terrain: {args.input} (format: {fmt.upper()})")
    print("-" * 50)

    try:
        terrain = load_terrain(args.input)
    except Exception as e:
        print(f"Error loading terrain: {e}")
        return 1

    stats = terrain.get_stats()

    print(f"File: {args.input}")
    print(f"Format: {'DDS Heightfield' if fmt == 'dds' else 'MeshSet Terrain Tile'}")
    print(f"Dimensions: {stats['width']} x {stats['height']}")
    print(f"Min height: {stats['min']}")
    print(f"Max height: {stats['max']}")
    print(f"Avg height: {stats['avg']:.2f}")

    if fmt == 'meshset' and isinstance(terrain, MeshSetTerrain):
        print(f"Scale: ({terrain.scale_x:.4f}, {terrain.scale_y:.4f})")
        print(f"Range: ({terrain.range_min:.4f}, {terrain.range_max:.4f})")
        print(f"Material path: {terrain.material_path}")

    # Show a small sample of the heightmap
    height_data = getattr(terrain, 'height_data', None) or getattr(terrain, 'heightmap', None)
    if args.verbose and height_data:
        print("\nHeightmap sample (top-left 8x8):")
        for y in range(min(8, terrain.height)):
            row = []
            for x in range(min(8, terrain.width)):
                row.append(f"{height_data[y][x]:3d}")
            print("  " + " ".join(row))

    print("-" * 50)
    return 0


def cmd_edit_height(args):
    """Raise or lower terrain in a region."""
    if not validate_input_file(args.input):
        return 1

    fmt = detect_format(args.input)
    print(f"\nEditing terrain: {args.input} (format: {fmt.upper()})")
    print("-" * 50)

    try:
        terrain = load_terrain(args.input)
    except Exception as e:
        print(f"Error loading terrain: {e}")
        return 1

    stats_before = terrain.get_stats()
    print(f"Before: min={stats_before['min']}, max={stats_before['max']}, avg={stats_before['avg']:.2f}")

    # Apply height edit
    terrain.edit_height_region(args.x1, args.y1, args.x2, args.y2, args.delta)

    stats_after = terrain.get_stats()
    print(f"After: min={stats_after['min']}, max={stats_after['max']}, avg={stats_after['avg']:.2f}")

    # Save
    print(f"\nSaving to: {args.output}")
    try:
        terrain.save(args.output)
        print("Save complete.")
    except Exception as e:
        print(f"Error saving terrain: {e}")
        return 1

    # Optional export
    if args.export:
        try:
            terrain.export_image(args.export)
        except Exception as e:
            print(f"Warning: Export failed: {e}")

    print("-" * 50)
    return 0


def cmd_smooth(args):
    """Apply box blur to terrain region."""
    if not validate_input_file(args.input):
        return 1

    fmt = detect_format(args.input)
    print(f"\nSmoothing terrain: {args.input} (format: {fmt.upper()})")
    print("-" * 50)

    try:
        terrain = load_terrain(args.input)
    except Exception as e:
        print(f"Error loading terrain: {e}")
        return 1

    stats_before = terrain.get_stats()
    print(f"Before: min={stats_before['min']}, max={stats_before['max']}, avg={stats_before['avg']:.2f}")

    # Apply smoothing
    terrain.smooth_region(args.x1, args.y1, args.x2, args.y2, args.iterations)

    stats_after = terrain.get_stats()
    print(f"After: min={stats_after['min']}, max={stats_after['max']}, avg={stats_after['avg']:.2f}")

    # Save
    print(f"\nSaving to: {args.output}")
    try:
        terrain.save(args.output)
        print("Save complete.")
    except Exception as e:
        print(f"Error saving terrain: {e}")
        return 1

    print("-" * 50)
    return 0


def cmd_export_image(args):
    """Export terrain as PNG visualization."""
    if not validate_input_file(args.input):
        return 1

    fmt = detect_format(args.input)
    print(f"\nExporting terrain: {args.input} (format: {fmt.upper()})")

    try:
        terrain = load_terrain(args.input)
        terrain.export_image(args.output)
    except Exception as e:
        print(f"Error exporting terrain: {e}")
        return 1

    return 0


def cmd_create(args):
    """Generate a minimal test terrain tile from scratch."""
    print(f"\nCreating terrain tile: {args.output}")
    print("-" * 50)
    print(f"Type: {args.type.upper()}")
    print(f"Size: {args.size}x{args.size}")
    print(f"Height: {args.height}")

    if args.type == 'dds':
        terrain = DDSHeightfield()
        terrain.width = args.size
        terrain.height = args.size

        # Create heightmap based on mode
        terrain.heightmap = [[0] * args.size for _ in range(args.size)]

        if args.mode == 'flat':
            for y in range(args.size):
                for x in range(args.size):
                    terrain.heightmap[y][x] = args.height
        elif args.mode == 'slope':
            # Diagonal slope
            for y in range(args.size):
                for x in range(args.size):
                    val = args.height + (x + y) // 4
                    terrain.heightmap[y][x] = max(0, min(255, val))
        elif args.mode == 'hill':
            # Simple circular hill in center
            cx, cy = args.size // 2, args.size // 2
            radius = args.size // 3
            for y in range(args.size):
                for x in range(args.size):
                    dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
                    if dist < radius:
                        val = args.height + int((radius - dist) * 2)
                    else:
                        val = args.height
                    terrain.heightmap[y][x] = max(0, min(255, val))
        elif args.mode == 'noise':
            # Pseudo-random noise (deterministic based on position)
            for y in range(args.size):
                for x in range(args.size):
                    val = args.height + ((x * 7 + y * 13 + x * y) % 64)
                    terrain.heightmap[y][x] = max(0, min(255, val))

    elif args.type == 'meshset':
        terrain = MeshSetTerrain()
        terrain.width = args.size
        terrain.height = args.size
        terrain.scale_x = 1.0
        terrain.scale_y = 1.0
        terrain.range_min = 0.0
        terrain.range_max = float(args.height)
        terrain.material_path = "environments/materials/test_terrain"

        # Create heightmap based on mode
        terrain.height_data = [[0] * args.size for _ in range(args.size)]

        if args.mode == 'flat':
            for y in range(args.size):
                for x in range(args.size):
                    terrain.height_data[y][x] = args.height
        elif args.mode == 'slope':
            # Diagonal slope
            for y in range(args.size):
                for x in range(args.size):
                    val = args.height + (x + y) // 4
                    terrain.height_data[y][x] = max(0, min(255, val))
        elif args.mode == 'hill':
            # Simple circular hill in center
            cx, cy = args.size // 2, args.size // 2
            radius = args.size // 3
            for y in range(args.size):
                for x in range(args.size):
                    dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
                    if dist < radius:
                        val = args.height + int((radius - dist) * 2)
                    else:
                        val = args.height
                    terrain.height_data[y][x] = max(0, min(255, val))
        elif args.mode == 'noise':
            # Pseudo-random noise (deterministic based on position)
            for y in range(args.size):
                for x in range(args.size):
                    val = args.height + ((x * 7 + y * 13 + x * y) % 64)
                    terrain.height_data[y][x] = max(0, min(255, val))

    else:
        print(f"Error: Unknown terrain type: {args.type}")
        return 1

    stats = terrain.get_stats()
    print(f"Created: min={stats['min']}, max={stats['max']}, avg={stats['avg']:.2f}")

    # Save
    print(f"\nSaving to: {args.output}")
    try:
        terrain.save(args.output)
        print("Save complete.")
    except Exception as e:
        print(f"Error saving terrain: {e}")
        return 1

    # Optional export
    if args.export:
        try:
            terrain.export_image(args.export)
        except Exception as e:
            print(f"Warning: Export failed: {e}")

    print("-" * 50)
    return 0


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """Main entry point with argparse CLI."""
    parser = argparse.ArgumentParser(
        description='Brutal Legend Terrain Editor - Edit terrain data (DDS and MeshSet formats)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s view input.Heightfield
  %(prog)s view worlds/continent3/tile/x0/y0/height.bin
  %(prog)s edit-height input.Heightfield output.Heightfield --x1 0 --y1 0 --x2 64 --y2 64 --delta 20
  %(prog)s smooth input.Heightfield output.Heightfield --x1 32 --y1 32 --x2 96 --y2 96
  %(prog)s export-image input.Heightfield --output terrain.png
  %(prog)s create output.Heightfield --type dds --size 128 --mode hill --height 64
  %(prog)s create height.bin --type meshset --size 46 --mode flat --height 128
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # view command
    view_parser = subparsers.add_parser('view', help='Display terrain data as text summary')
    view_parser.add_argument('input', help='Input terrain file (DDS or MeshSet height.bin)')
    view_parser.add_argument('--verbose', '-v', action='store_true', help='Show heightmap sample')

    # edit-height command
    edit_parser = subparsers.add_parser('edit-height', help='Raise/lower terrain in a region')
    edit_parser.add_argument('input', help='Input terrain file')
    edit_parser.add_argument('output', help='Output terrain file')
    edit_parser.add_argument('--x1', type=int, required=True, help='Top-left X coordinate')
    edit_parser.add_argument('--y1', type=int, required=True, help='Top-left Y coordinate')
    edit_parser.add_argument('--x2', type=int, required=True, help='Bottom-right X coordinate')
    edit_parser.add_argument('--y2', type=int, required=True, help='Bottom-right Y coordinate')
    edit_parser.add_argument('--delta', type=int, required=True, help='Height change (+/-)')
    edit_parser.add_argument('--export', help='Export result to PNG file')

    # smooth command
    smooth_parser = subparsers.add_parser('smooth', help='Apply box blur to terrain region')
    smooth_parser.add_argument('input', help='Input terrain file')
    smooth_parser.add_argument('output', help='Output terrain file')
    smooth_parser.add_argument('--x1', type=int, required=True, help='Top-left X coordinate')
    smooth_parser.add_argument('--y1', type=int, required=True, help='Top-left Y coordinate')
    smooth_parser.add_argument('--x2', type=int, required=True, help='Bottom-right X coordinate')
    smooth_parser.add_argument('--y2', type=int, required=True, help='Bottom-right Y coordinate')
    smooth_parser.add_argument('--iterations', type=int, default=1, help='Number of blur passes (default: 1)')

    # export-image command
    export_parser = subparsers.add_parser('export-image', help='Export as PNG visualization')
    export_parser.add_argument('input', help='Input terrain file')
    export_parser.add_argument('--output', '-o', required=True, help='Output PNG file')

    # create command
    create_parser = subparsers.add_parser('create', help='Generate a minimal test terrain tile')
    create_parser.add_argument('output', help='Output terrain file')
    create_parser.add_argument('--type', '-t', choices=['dds', 'meshset'], default='meshset',
                                help='Terrain format type (default: meshset)')
    create_parser.add_argument('--size', '-s', type=int, default=46,
                                help='Terrain size (default: 46 for meshset, 128 for dds)')
    create_parser.add_argument('--height', type=int, default=128,
                                help='Base height value 0-255 (default: 128)')
    create_parser.add_argument('--mode', '-m', choices=['flat', 'slope', 'hill', 'noise'],
                                default='flat', help='Terrain shape mode (default: flat)')
    create_parser.add_argument('--export', help='Export result to PNG file')

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 1

    if args.command == 'view':
        return cmd_view(args)
    elif args.command == 'edit-height':
        return cmd_edit_height(args)
    elif args.command == 'smooth':
        return cmd_smooth(args)
    elif args.command == 'export-image':
        return cmd_export_image(args)
    elif args.command == 'create':
        return cmd_create(args)
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())
