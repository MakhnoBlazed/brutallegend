#!/usr/bin/env python3
"""
Brutal Legend Test Map Creator
==============================
Creates a minimal test map tile that can be loaded through the mod loader.

The tile uses coordinates x=100, y=100 which are outside the continent3
range (x=-8 to +6, y=-8 to +7) to avoid conflicts with real terrain.

Usage:
    python create_test_map.py [--output-dir OUTPUT_DIR]

Output:
    test_map/
        RgS_TestWorld.~h    (DFPF header file)
        RgS_TestWorld.~p    (DFPF data file)
"""

import struct
import zlib
import os
import sys
import argparse
from pathlib import Path
from typing import List, Dict, Tuple

# Game install path - adjust if needed
DEFAULT_GAME_PATH = r"C:\Users\kevin\OneDrive\Desktop\steam\steamapps\common\BrutalLegend"

# Tile coordinates outside normal range
TEST_TILE_X = 100
TEST_TILE_Y = 100
TEST_WORLD_NAME = "testworld"

# Compression types from dfpf_repack.py
COMPRESSION_UNCOMPRESSED_V5 = 4
COMPRESSION_ZLIB_V5 = 8


class FileRecord:
    """Represents a file record in the DFPF container."""
    def __init__(self):
        self.filename: str = ""
        self.extension: str = ""
        self.uncompressed_size: int = 0
        self.offset: int = 0
        self.size: int = 0
        self.file_type_index: int = 0
        self.compression_type: int = COMPRESSION_ZLIB_V5
        self.data: bytes = b''


class DFPFCreator:
    """Creates a DFPF V5 container from file data."""
    MAGIC = b"dfpf"
    VERSION = 5
    HEADER_SIZE = 88
    MARKER_VALUE = 0x23A1CEAB

    def __init__(self):
        self.file_extensions: List[str] = []
        self.records: List[FileRecord] = []

    def add_file(self, filename: str, extension: str, data: bytes, file_type_index: int = 0):
        """Add a file to the DFPF container."""
        record = FileRecord()
        record.filename = filename
        record.extension = extension
        record.file_type_index = file_type_index

        # Compress data if it compresses well
        if len(data) > 0:
            compressed = zlib.compress(data, 9)
            if len(compressed) < len(data):
                record.data = compressed
                record.compression_type = COMPRESSION_ZLIB_V5
                record.size = len(compressed)
            else:
                record.compression_type = COMPRESSION_UNCOMPRESSED_V5
                record.size = len(data)
                record.data = data
        else:
            record.compression_type = COMPRESSION_UNCOMPRESSED_V5
            record.size = 0

        record.uncompressed_size = len(data)
        self.records.append(record)

        # Add extension if not already present
        if extension not in self.file_extensions:
            self.file_extensions.append(extension)

    def _pack_file_record(self, record: FileRecord, name_offset: int) -> bytes:
        """Pack a file record into 16 bytes (V5 format)."""
        raw_dword0 = record.uncompressed_size << 8
        raw_dword1 = name_offset << 11
        raw_dword2 = (record.offset << 3) | (record.size & 0xFFFFFFF0)
        raw_dword3 = ((record.file_type_index * 2) << 20) | (record.compression_type & 0x0F)
        return struct.pack(">IIII", raw_dword0, raw_dword1, raw_dword2, raw_dword3)

    def save(self, output_path: str) -> Tuple[Path, Path]:
        """Save the DFPF container to .~h and .~p files."""
        out_path = Path(output_path)
        header_out = out_path.with_suffix(".~h")
        data_out = out_path.with_suffix(".~p")

        print(f"Creating DFPF container: {header_out}")

        # Build name directory
        name_dir = b''
        name_offsets: Dict[int, int] = {}

        for i, rec in enumerate(self.records):
            name_offsets[i] = len(name_dir)
            name_dir += rec.filename.encode('ascii') + b'\x00'

        name_dir_size = len(name_dir)

        # Calculate offsets
        header_fixed_size = 4 + 1 + 3 + self.HEADER_SIZE  # 96 bytes
        ext_table_size = len(self.file_extensions) * 16
        file_records_size = len(self.records) * 16

        file_ext_offset = header_fixed_size
        name_dir_offset = file_ext_offset + ext_table_size
        file_records_offset = name_dir_offset + name_dir_size

        # Build the .~p data file
        data_parts = []
        current_offset = 0

        for rec in self.records:
            rec.offset = current_offset
            data_parts.append(rec.data)
            current_offset += rec.size

        with open(data_out, 'wb') as f:
            for data in data_parts:
                f.write(data)

        # Build the .~h header file
        with open(header_out, 'wb') as f:
            # Magic
            f.write(self.MAGIC)
            # Version
            f.write(struct.pack("B", self.VERSION))
            # Padding
            f.write(b'\x00' * 3)

            # Header struct (88 bytes)
            header_data = bytearray(self.HEADER_SIZE)

            struct.pack_into(">Q", header_data, 0, file_ext_offset)
            struct.pack_into(">Q", header_data, 8, name_dir_offset)
            struct.pack_into(">I", header_data, 16, len(self.file_extensions))
            struct.pack_into(">I", header_data, 20, name_dir_size)
            struct.pack_into(">I", header_data, 24, len(self.records))
            struct.pack_into(">I", header_data, 28, self.MARKER_VALUE)
            struct.pack_into(">I", header_data, 32, 0)  # blank_bytes1
            struct.pack_into(">I", header_data, 36, 0)  # blank_bytes2
            struct.pack_into(">Q", header_data, 40, current_offset)  # junk_data_offset
            struct.pack_into(">Q", header_data, 48, file_records_offset)
            struct.pack_into(">Q", header_data, 56, 0)  # footer_offset1
            struct.pack_into(">Q", header_data, 64, 0)  # footer_offset2
            struct.pack_into(">I", header_data, 72, 0)  # unknown
            struct.pack_into(">I", header_data, 76, self.MARKER_VALUE)

            f.write(header_data)

            # File extension table
            for ext_name in self.file_extensions:
                ext_bytes = ext_name.encode('ascii')
                ext_entry = struct.pack(">I", len(ext_bytes)) + ext_bytes + b'\x00' * 12
                f.write(ext_entry)

            # Name directory
            f.write(name_dir)

            # File records
            for i, rec in enumerate(self.records):
                rec_bytes = self._pack_file_record(rec, name_offsets[i])
                f.write(rec_bytes)

        print(f"Created {header_out} ({Path(header_out).stat().st_size} bytes)")
        print(f"Created {data_out} ({Path(data_out).stat().st_size} bytes)")

        return header_out, data_out


def create_height_bin() -> bytes:
    """
    Create a minimal height.bin file.
    Format: HSEM header + data section with material indices.
    """
    # Build the header (based on TERRAIN_SPEC.md analysis)
    # Magic: "hsem" (mesh backwards)
    # Followed by various metadata floats and "lrtm" marker

    header = bytearray()

    # hsem magic
    header.extend(b'hsem')

    # Unknown 4 bytes (0x00000000)
    header.extend(struct.pack('>I', 0x00000000))

    # Floats at 0x08: possibly scale values (1.27, 0.897)
    header.extend(struct.pack('>f', 1.27))
    header.extend(struct.pack('>f', 0.897))

    # Floats at 0x10: possibly height range
    header.extend(struct.pack('>f', 0.0))
    header.extend(struct.pack('>f', 100.0))

    # Floats at 0x18
    header.extend(struct.pack('>f', 0.0))
    header.extend(struct.pack('>f', 0.0))

    # lrtm magic (terrain marker) at 0x20
    header.extend(b'lrtm')

    # Version at 0x24: 0x01000000
    header.extend(struct.pack('>I', 0x01000000))

    # Count at 0x28: number of entries
    header.extend(struct.pack('>I', 0x0000002E))  # 46 entries

    # String section starts at 0x2C
    # Reference to materials string
    mat_string = b'environments/materials/terrain/rock_sand\x00'
    header.extend(mat_string)

    # Pad to 0x70 for BVXD marker
    while len(header) < 0x70:
        header.append(0)

    # BVXD marker at 0x70
    header.extend(b'BVXD')

    # Unknown at 0x74
    header.extend(struct.pack('>I', 0x02000000))

    # Unknown at 0x78
    header.extend(struct.pack('>I', 0x00000000))

    # BIXD marker at 0x7C
    header.extend(b'BIXD')

    # Data section: uint16 material indices (0x0400-0x04FF range)
    # Create a 16x16 grid of material indices for a simple pattern
    data = bytearray()
    for y in range(16):
        for x in range(16):
            # Simple gradient pattern
            idx = 0x0400 + ((x + y) % 16) * 16
            data.extend(struct.pack('>H', idx))

    return bytes(header) + bytes(data)


def create_blend_bin() -> bytes:
    """
    Create a minimal blend.bin file.
    Similar structure to height.bin with HSEM header.
    """
    header = bytearray()

    # hsem magic
    header.extend(b'hsem')

    # Unknown 4 bytes
    header.extend(struct.pack('>I', 0x00000000))

    # Scale floats
    header.extend(struct.pack('>f', 1.0))
    header.extend(struct.pack('>f', 1.0))

    # Height range
    header.extend(struct.pack('>f', 0.0))
    header.extend(struct.pack('>f', 255.0))

    # More floats
    header.extend(struct.pack('>f', 0.0))
    header.extend(struct.pack('>f', 0.0))

    # lrtm magic
    header.extend(b'lrtm')

    # Version
    header.extend(struct.pack('>I', 0x01000000))

    # Count
    header.extend(struct.pack('>I', 0x00000002))  # 2 entries

    # Material strings
    mat1 = b'environments/terrainmaterials/sandbeach\x00'
    header.extend(mat1)
    mat2 = b'environments/terrainmaterials/introrockcliff\x00'
    header.extend(mat2)

    # Pad to 0x70
    while len(header) < 0x70:
        header.append(0)

    # BVXD marker
    header.extend(b'BVXD')
    header.extend(struct.pack('>I', 0x02000000))
    header.extend(struct.pack('>I', 0x00000000))
    header.extend(b'BIXD')

    # Data section: simple pattern
    data = bytearray()
    for y in range(16):
        for x in range(16):
            idx = 0x0001 if (x + y) % 2 == 0 else 0x0002
            data.extend(struct.pack('>H', idx))

    return bytes(header) + bytes(data)


def create_blend_texture(tile_x: int, tile_y: int, world_name: str) -> bytes:
    """
    Create a blend.Texture metadata file.
    Format based on TERRAIN_SPEC.md section 3.1.
    """
    data = bytearray()

    # Header (16 bytes)
    # Magic: 0x00000001 (little-endian)
    data.extend(struct.pack('<I', 0x00000001))
    # Version: 4
    data.extend(struct.pack('<I', 4))
    # Flags: 0x3F800000 (float 1.0)
    data.extend(struct.pack('<I', 0x3F800000))
    # Unknown: 0x00000025
    data.extend(struct.pack('<I', 0x00000025))

    # blend_path string (null-terminated)
    blend_path = f"worlds/{world_name}/tile/x{tile_x}/y{tile_y}/blend"
    data.extend(blend_path.encode('ascii') + b'\x00')

    # Occlusion path (length-prefixed)
    occlusion_path = f"worlds/{world_name}/tile/x{tile_x}/y{tile_y}/occlusion"
    occ_bytes = occlusion_path.encode('ascii') + b'\x00'
    data.extend(struct.pack('<I', len(occ_bytes)))
    data.extend(occ_bytes)

    # Material count: 1
    data.extend(struct.pack('<I', 1))

    # Material string 1 (length-prefixed)
    mat1_path = "environments/terrainmaterials/sandbeach"
    mat1_bytes = mat1_path.encode('ascii') + b'\x00'
    data.extend(struct.pack('<I', len(mat1_bytes)))
    data.extend(mat1_bytes)

    return bytes(data)


def create_occlusion_texture(tile_x: int, tile_y: int, world_name: str) -> bytes:
    """
    Create an occlusion.Texture metadata file.
    """
    data = bytearray()

    # Header (16 bytes)
    data.extend(struct.pack('<I', 0x00000001))
    data.extend(struct.pack('<I', 4))
    data.extend(struct.pack('<I', 0x3F800000))
    data.extend(struct.pack('<I', 0x00000025))

    # occlusion_path string (null-terminated)
    occlusion_path = f"worlds/{world_name}/tile/x{tile_x}/y{tile_y}/occlusion"
    data.extend(occlusion_path.encode('ascii') + b'\x00')

    # (No occlusion texture reference for now - minimal file)
    # Just add a null to terminate
    data.extend(b'\x00')

    return bytes(data)


def create_tile(tile_x: int, tile_y: int, world_name: str) -> Dict[str, bytes]:
    """Create all files for a single tile."""
    files = {}

    # Build the tile path prefix
    tile_path = f"worlds/{world_name}/tile/x{tile_x}/y{tile_y}"

    # Create height.bin
    files[f"{tile_path}/height.bin"] = create_height_bin()

    # Create blend.bin
    files[f"{tile_path}/blend.bin"] = create_blend_bin()

    # Create blend.Texture
    files[f"{tile_path}/blend.Texture"] = create_blend_texture(tile_x, tile_y, world_name)

    # Create occlusion.Texture
    files[f"{tile_path}/occlusion.Texture"] = create_occlusion_texture(tile_x, tile_y, world_name)

    return files


def create_test_map(output_dir: str, game_path: str = DEFAULT_GAME_PATH):
    """Create a complete test map bundle."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    print(f"Creating test map in {output_path}")
    print(f"Tile coordinates: x={TEST_TILE_X}, y={TEST_TILE_Y}")
    print(f"World name: {TEST_WORLD_NAME}")

    # Create tile files
    tile_files = create_tile(TEST_TILE_X, TEST_TILE_Y, TEST_WORLD_NAME)

    # Create DFPF container
    bundle_name = f"RgS_{TEST_WORLD_NAME.capitalize()}"
    creator = DFPFCreator()

    # Add each file to the container
    # Extension to type index mapping
    ext_to_idx = {
        'bin': 0,
        'Texture': 1,
    }

    for filepath, filedata in tile_files.items():
        # Extract extension from path
        ext = filepath.split('.')[-1]
        file_type_idx = ext_to_idx.get(ext, 0)

        # Use just the world/tile path as filename
        # e.g., "worlds/testworld/tile/x100/y100/height.bin"
        creator.add_file(filepath, ext, filedata, file_type_idx)

    # Save the DFPF bundle
    header_path, data_path = creator.save(str(output_path / bundle_name))

    print(f"\nTest map created successfully!")
    print(f"Bundle files:")
    print(f"  {header_path}")
    print(f"  {data_path}")
    print(f"\nTo load the test map:")
    print(f"  1. Copy {header_path.name} and {data_path.name} to:")
    print(f"     {game_path}\\Win\\Mods\\")
    print(f"  2. Launch the game with the mod loader")
    print(f"  3. The game will attempt to load tile x={TEST_TILE_X}, y={TEST_TILE_Y}")

    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Create a minimal test map for Brutal Legend modding",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
    python create_test_map.py --output-dir test_map
        """
    )
    parser.add_argument(
        '--output-dir', '-o',
        default='test_map',
        help='Output directory for the test map (default: test_map)'
    )
    parser.add_argument(
        '--game-path',
        default=DEFAULT_GAME_PATH,
        help=f'Game install path (default: {DEFAULT_GAME_PATH})'
    )

    args = parser.parse_args()

    try:
        output_path = create_test_map(args.output_dir, args.game_path)
        print(f"\nDone! Test map files are in: {output_path.absolute()}")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
