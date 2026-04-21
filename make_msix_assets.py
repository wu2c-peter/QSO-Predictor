"""
Generate MSIX package icon assets from logo.png.

Produces the PNG assets required for Microsoft Store MSIX submission.
Output goes to packaging/Assets/ ready to be referenced from AppxManifest.xml.

Run:
    python make_msix_assets.py

Requires Pillow:
    pip install Pillow
"""

from PIL import Image
from pathlib import Path

SOURCE = "logo.png"
OUTPUT_DIR = Path("packaging/Assets")

# Required MSIX asset sizes.
# Format: (filename, width, height)
# See: https://learn.microsoft.com/en-us/windows/apps/design/style/iconography/app-icon-construction
ASSETS = [
    # Required minimum set for Store submission
    ("StoreLogo.png", 50, 50),              # Store listing page
    ("Square44x44Logo.png", 44, 44),        # Taskbar, small tile
    ("Square150x150Logo.png", 150, 150),    # Medium tile (Start menu)
    ("Wide310x150Logo.png", 310, 150),      # Wide tile (Start)
    ("Square310x310Logo.png", 310, 310),    # Large tile
    ("Square71x71Logo.png", 71, 71),        # Small tile
    ("SplashScreen.png", 620, 300),         # Launch splash
    ("LockScreenLogo.png", 24, 24),         # Lock screen badge
    
    # Scale variants (scale-100, scale-125, scale-150, scale-200, scale-400)
    # MSIX requires these for proper rendering on high-DPI displays.
    # Scale-100 is the base; others are upscaled from logo for higher DPI.
    ("Square44x44Logo.scale-100.png", 44, 44),
    ("Square44x44Logo.scale-125.png", 55, 55),
    ("Square44x44Logo.scale-150.png", 66, 66),
    ("Square44x44Logo.scale-200.png", 88, 88),
    ("Square44x44Logo.scale-400.png", 176, 176),
    
    ("Square150x150Logo.scale-100.png", 150, 150),
    ("Square150x150Logo.scale-125.png", 188, 188),
    ("Square150x150Logo.scale-150.png", 225, 225),
    ("Square150x150Logo.scale-200.png", 300, 300),
    ("Square150x150Logo.scale-400.png", 600, 600),
    
    ("StoreLogo.scale-100.png", 50, 50),
    ("StoreLogo.scale-125.png", 63, 63),
    ("StoreLogo.scale-150.png", 75, 75),
    ("StoreLogo.scale-200.png", 100, 100),
    ("StoreLogo.scale-400.png", 200, 200),
    
    # Target size variants for 44x44 (for various UI surfaces)
    # These are needed for taskbar, task switcher, etc.
    ("Square44x44Logo.targetsize-16.png", 16, 16),
    ("Square44x44Logo.targetsize-24.png", 24, 24),
    ("Square44x44Logo.targetsize-32.png", 32, 32),
    ("Square44x44Logo.targetsize-48.png", 48, 48),
    ("Square44x44Logo.targetsize-256.png", 256, 256),
]


def fit_logo(source_img, target_width, target_height, background=(40, 25, 60, 255)):
    """Fit the source logo into a target size.
    
    For square-to-square: direct resize with high-quality downsample.
    For square-to-wide (like 310x150 wide tile): center the logo on a background.
    
    background color matches QSOP logo's dark purple aesthetic.
    """
    src_w, src_h = source_img.size
    
    if target_width == target_height:
        # Square target — direct resize
        return source_img.resize((target_width, target_height), Image.Resampling.LANCZOS)
    else:
        # Wide/non-square target — center the logo on background
        canvas = Image.new("RGBA", (target_width, target_height), background)
        # Scale logo to fit the smaller dimension (height for wide tiles)
        scale = min(target_width, target_height) / max(src_w, src_h)
        logo_w = int(src_w * scale * 0.85)  # 85% to leave some padding
        logo_h = int(src_h * scale * 0.85)
        logo_resized = source_img.resize((logo_w, logo_h), Image.Resampling.LANCZOS)
        # Center on canvas
        x = (target_width - logo_w) // 2
        y = (target_height - logo_h) // 2
        canvas.paste(logo_resized, (x, y), logo_resized if logo_resized.mode == "RGBA" else None)
        return canvas


def main():
    source_path = Path(SOURCE)
    if not source_path.exists():
        print(f"Error: Could not find '{SOURCE}' in current directory.")
        print(f"Run from the repo root where logo.png lives.")
        return 1
    
    # Load source
    print(f"Loading {SOURCE}...")
    img = Image.open(source_path)
    print(f"  Source size: {img.size[0]}x{img.size[1]} ({img.mode})")
    
    # Ensure RGBA for transparency support
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    
    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {OUTPUT_DIR}")
    
    # Generate each asset
    print(f"\nGenerating {len(ASSETS)} asset files...")
    for filename, w, h in ASSETS:
        output_path = OUTPUT_DIR / filename
        resized = fit_logo(img, w, h)
        resized.save(output_path, format="PNG", optimize=True)
        print(f"  {filename:45s} {w:4d}x{h:<4d}")
    
    print(f"\nDone! Generated {len(ASSETS)} assets in {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
