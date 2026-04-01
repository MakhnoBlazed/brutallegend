#!/bin/bash
# Brutal Legend Test Map Loader (Unix/macOS)
# Copies test map to Win/Mods/ and optionally launches the game with wine

# Game install path - adjust if your install is different
GAME_PATH="${GAME_PATH:-$HOME/.wine/drive_c/Program Files/Steam/steamapps/common/BrutalLegend}"
MOD_PATH="$GAME_PATH/Win/Mods"

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TEST_MAP_DIR="$SCRIPT_DIR/test_map"
BUNDLE_NAME="RgS_Testworld"

echo "================================================"
echo "Brutal Legend Test Map Loader"
echo "================================================"
echo ""

# Check if game path exists
if [ ! -f "$GAME_PATH/BrutalLegend.exe" ]; then
    # Try alternative paths
    if [ -f "/mnt/c/Program Files/Steam/steamapps/common/BrutalLegend/BrutalLegend.exe" ]; then
        GAME_PATH="/mnt/c/Program Files/Steam/steamapps/common/BrutalLegend"
    elif [ -f "$HOME/Library/Application Support/Steam/steamapps/common/Brutal Legend/Brutal Legend.exe" ]; then
        GAME_PATH="$HOME/Library/Application Support/Steam/steamapps/common/Brutal Legend"
    else
        echo "ERROR: Game not found at:"
        echo "  $GAME_PATH/BrutalLegend.exe"
        echo ""
        echo "Please set GAME_PATH environment variable or update this script."
        echo ""
        read -p "Press Enter to exit..."
        exit 1
    fi
fi

MOD_PATH="$GAME_PATH/Win/Mods"

# Create mod directory if it doesn't exist
if [ ! -d "$MOD_PATH" ]; then
    echo "Creating mod directory: $MOD_PATH"
    mkdir -p "$MOD_PATH"
fi

# Check if test map exists
if [ ! -d "$TEST_MAP_DIR" ]; then
    echo "ERROR: Test map not found at:"
    echo "  $TEST_MAP_DIR"
    echo ""
    echo "Please run create_test_map.py first:"
    echo "  python create_test_map.py"
    echo ""
    read -p "Press Enter to exit..."
    exit 1
fi

# Copy the test map bundle files to Win/Mods
echo "Copying test map to Win/Mods/..."
echo ""

COPIED=0
for f in "$TEST_MAP_DIR/$BUNDLE_NAME".*; do
    if [ -f "$f" ]; then
        filename=$(basename "$f")
        echo "  Copying: $filename"
        cp -f "$f" "$MOD_PATH/"
        COPIED=$((COPIED + 1))
    fi
done

if [ $COPIED -eq 0 ]; then
    echo "ERROR: No bundle files found in $TEST_MAP_DIR"
    echo "Expected files: $BUNDLE_NAME.~h and $BUNDLE_NAME.~p"
    echo ""
    echo "Please run create_test_map.py first:"
    echo "  python create_test_map.py"
    echo ""
    read -p "Press Enter to exit..."
    exit 1
fi

echo ""
echo "Successfully copied $COPIED files to $MOD_PATH"
echo ""

# Ask if user wants to launch the game
read -p "Launch the game now? (Y/N): " LAUNCH
if [[ "$LAUNCH" =~ ^[Yy]$ ]]; then
    echo ""
    echo "Launching Brutal Legend..."

    # Check if running on Windows (Git Bash, WSL, etc.)
    if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" || -n "$WINDIR" ]]; then
        # Windows - use start command
        start "" "$GAME_PATH/BrutalLegend.exe"
    elif command -v wine &> /dev/null; then
        # Linux with Wine
        wine "$GAME_PATH/BrutalLegend.exe"
    else
        echo "Warning: Could not detect how to launch the game."
        echo "Please launch manually: $GAME_PATH/BrutalLegend.exe"
    fi
else
    echo ""
    echo "Skipping game launch."
    echo "To play with the test map, manually run:"
    echo "  $GAME_PATH/BrutalLegend.exe"
fi

echo ""
echo "================================================"
echo "Test map installed!"
echo ""
echo "To verify installation, check that these files exist:"
echo "  $MOD_PATH/$BUNDLE_NAME.~h"
echo "  $MOD_PATH/$BUNDLE_NAME.~p"
echo ""
echo "Note: The mod loader (buddha_mod.dll) must be installed"
echo "and active for the test map to load."
echo "================================================"

read -p "Press Enter to exit..."
