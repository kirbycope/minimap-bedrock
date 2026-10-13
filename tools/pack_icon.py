"""Draws the pack icon both packs show in Minecraft's add-on list.

It is the map itself: a few rows of the real palette with the real player arrow in the middle, so the
icon cannot drift from what the add-on actually draws.

    python tools/pack_icon.py            # write both pack_icon.png files
    python tools/pack_icon.py --check    # exit 1 if either is out of date
"""

import argparse
import io
import os
import sys

from PIL import Image

import palette

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKS = (
    os.path.join(ROOT, "development_behavior_packs", "minimap", "pack_icon.png"),
    os.path.join(ROOT, "development_resource_packs", "minimap", "pack_icon.png"),
)
SIZE = 256
GRID = 9        # cells across the icon, the add-on's own default map size
# a small scene: water on the left, sand, grass with a path through it
SCENE = """
wwsggggrg
wwsgggrgg
wwsggrggg
wwsgrgggg
wwsgPgggg
wwsgrgggg
wwssgrggg
wwwsggrgg
wwwsgggrg
"""
LOOKUP = {"w": "water", "s": "sand", "g": "grass", "r": "dirt", "P": "grass"}


def icon() -> Image.Image:
    rows = [row for row in SCENE.strip().splitlines()]
    cell = SIZE // (GRID + 2)
    image = Image.new("RGBA", (SIZE, SIZE), (*palette.COLOURS["border"], 255))
    for y, row in enumerate(rows):
        for x, key in enumerate(row):
            colour = palette.shaded(palette.COLOURS[LOOKUP[key]], palette.SHADES[0 if (x + y) % 3 == 0 else 1])
            box = ((x + 1) * cell, (y + 1) * cell, (x + 2) * cell, (y + 2) * cell)
            image.paste(Image.new("RGBA", (cell, cell), colour), box[:2])
    arrow = palette.arrow("n").resize((cell * 2, cell * 2), Image.NEAREST)
    image.paste(arrow, ((GRID // 2) * cell, (GRID // 2) * cell))
    return image



def same(path, data):
    """Whether the file already holds this.

    PNGs are compared as images rather than as bytes, because two Pillow versions encode the same
    pixels into different files: the repository's copy and a fresh build matched here and read as
    stale on CI, which is a difference in the encoder, not in the picture.
    """
    if not os.path.exists(path):
        return False
    stored = open(path, "rb").read()
    if stored == data:
        return True
    if not path.lower().endswith(".png"):
        return False
    import io
    try:
        with Image.open(io.BytesIO(stored)) as a, Image.open(io.BytesIO(data)) as b:
            return a.size == b.size and a.convert("RGBA").tobytes() == b.convert("RGBA").tobytes()
    except Exception:
        return False

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="report whether the icons are up to date")
    args = parser.parse_args()

    buffer = io.BytesIO()
    icon().save(buffer, "PNG", optimize=True)
    data = buffer.getvalue()
    stale = []
    for path in PACKS:
        if same(path, data):
            continue
        stale.append(path)
        if not args.check:
            with open(path, "wb") as handle:
                handle.write(data)
    for path in PACKS:
        print(f"{'stale' if path in stale else 'ok   '} {os.path.relpath(path, ROOT)}")
    return 1 if args.check and stale else 0


if __name__ == "__main__":
    sys.exit(main())
