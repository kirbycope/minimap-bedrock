"""Writes the minimap's cell textures and the colour table the behaviour pack reads.

The map is drawn by the HUD layer in ui/hud_screen.json (written by tools/hud.py): a grid of image
controls, one per map cell, each showing the texture its two characters of the map title name. So a
colour is a 1x1 texture here, and a value is a cell's colour at one of its brightness steps.

    development_resource_packs/minimap/textures/ui/minimap/cNN.png     one per value, NN its two letters (see code())
    development_resource_packs/minimap/textures/ui/minimap/c.png       transparent, for no cell at all
    development_resource_packs/minimap/textures/ui/minimap/czz.png     transparent, past the map's edge
    development_resource_packs/minimap/textures/ui/minimap/arrowN.png  the player, eight ways
    development_resource_packs/minimap/textures/ui/minimap/letterN.png the compass letters N E S W
    development_behavior_packs/minimap/scripts/palette.js              block id -> colour, for the script

    python tools/palette.py            # write them
    python tools/palette.py --check    # exit 1 if any is out of date

A value is named by two lower case letters, its hex digits written a to p ("03" is "ad"): lower case
because a pack is unpacked onto Windows and macOS file systems, which do not tell "cA" from "ca", and
letters because JSON UI turns a slice of the title made only of digits into a number, so "03" would
come out as 3 and name a texture that is not there. Two letters name up to 256 values, so the palette
can grow to Minecraft's full set of map colours and its four shades without the title or the HUD
changing shape.
"""

import argparse
import io
import json
import math
import os
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEXTURES = os.path.join(ROOT, "development_resource_packs", "minimap", "textures", "ui", "minimap")
SCRIPTS = os.path.join(ROOT, "development_behavior_packs", "minimap", "scripts")

SHADES = (0.71, 1.0)    # a cell takes the darker step when it is lower than the cell to its north
MARKER = 15         # pixels across the arrow texture, odd so the arrow has a middle column
MAX_VALUES = 256    # what two hex digits can name

# Minecraft's own map colours, the ones the map in your hand is drawn with. Thirty-two of them, from when
# the map was a font and every pair of values needed a glyph; a cell is an image now, so the cap is 256.
COLOURS: dict[str, tuple[int, int, int]] = {
    "unknown": (58, 58, 64),
    "border": (124, 100, 78),      # the parchment edge of the map item
    "grass": (127, 178, 56),
    "plant": (0, 124, 0),
    "dirt": (151, 109, 77),
    "podzol": (129, 86, 49),
    "sand": (247, 233, 163),
    "orange": (216, 127, 51),
    "light_gray": (153, 153, 153),
    "clay": (164, 168, 184),
    "stone": (112, 112, 112),
    "deepslate": (100, 100, 100),
    "water": (64, 64, 255),
    "ice": (160, 160, 255),
    "snow": (255, 255, 255),
    "wood": (143, 119, 72),
    "dark_wood": (76, 50, 35),
    "red": (153, 51, 51),
    "fire": (255, 0, 0),
    "nether": (112, 2, 0),
    "black": (25, 25, 25),
    "warped": (22, 126, 134),
    "crimson": (189, 48, 49),
    "gold": (250, 238, 77),
    "diamond": (92, 219, 213),
    "emerald": (0, 217, 58),
    "lapis": (74, 128, 255),
    "purple": (127, 63, 178),
    "pink": (242, 127, 165),
    "brown": (102, 76, 51),
    "green": (102, 127, 51),
    "gray": (76, 76, 76),
}

# The block lists below name more colours than there are, because they were written when a cell was a
# whole glyph and sixty-three colours fitted. These fold into the ones that are left, so the lists stay
# as they are and keep saying what a block looks like.
ALIASES = {
    "plants": "plant", "leaves": "plant", "cactus": "plant", "moss": "plant",
    "mycelium": "podzol", "mud": "dark_wood", "soul_soil": "dark_wood",
    "red_sand": "orange", "copper": "orange", "gravel": "light_gray", "glass": "light_gray",
    "iron": "light_gray", "bedrock": "black", "obsidian": "black", "coal": "black",
    "blackstone": "black", "nether_bricks": "black", "magma": "nether", "netherrack": "nether",
    "lava": "fire", "redstone": "fire", "bricks": "red", "end_stone": "sand", "quartz": "snow",
    "white": "snow", "prismarine": "warped", "cyan": "warped", "glowstone": "gold",
    "yellow": "gold", "lime": "emerald", "blue": "lapis", "light_blue": "lapis",
    "amethyst": "purple", "purpur": "purple", "magenta": "purple", "sea_lantern": "diamond",
}

# A block whose colour its name does not give away.
BLOCKS: dict[str, str] = {
    "grass_block": "grass",
    "short_grass": "plant",
    "tall_grass": "plant",
    "fern": "plant",
    "large_fern": "plant",
    "dead_bush": "wood",
    "sugar_cane": "plant",
    "bamboo": "plant",
    "lily_pad": "plant",
    "cactus": "plant",
    "pumpkin": "orange",
    "carved_pumpkin": "orange",
    "lit_pumpkin": "orange",
    "melon_block": "green",
    "hay_block": "gold",
    "dried_kelp_block": "green",
    "sponge": "gold",
    "wet_sponge": "gold",
    "coarse_dirt": "dirt",
    "rooted_dirt": "dirt",
    "dirt_with_roots": "dirt",
    "grass_path": "dirt",
    "podzol": "podzol",
    "mycelium": "podzol",
    "mud": "dark_wood",
    "packed_mud": "dirt",
    "soul_sand": "dark_wood",
    "magma": "nether",
    "shroomlight": "orange",
    "netherrack": "nether",
    "bedrock": "black",
    "crying_obsidian": "purple",
    "chest": "wood",
    "crafting_table": "wood",
    "barrel": "wood",
    "bookshelf": "wood",
    "ladder": "wood",
    "torch": "gold",
    "lantern": "gold",
    "soul_lantern": "warped",
    "campfire": "orange",
    "soul_campfire": "warped",
    "beacon": "diamond",
    "sculk": "black",
    "sculk_catalyst": "black",
    "sculk_sensor": "warped",
    "sculk_shrieker": "snow",
    "bone_block": "snow",
    "snow_layer": "snow",
    "powder_snow": "snow",
    "frosted_ice": "ice",
    "blue_ice": "ice",
    "packed_ice": "ice",
    "mangrove_roots": "dark_wood",
    "muddy_mangrove_roots": "dark_wood",
    "moss_block": "plant",
    "moss_carpet": "plant",
    "pale_moss_block": "light_gray",
    "pale_hanging_moss": "light_gray",
    "azalea_leaves": "plant",
    "azalea_leaves_flowered": "pink",
    "big_dripleaf": "plant",
    "small_dripleaf_block": "plant",
    "spore_blossom": "pink",
    "glow_lichen": "warped",
    "hanging_roots": "wood",
    "dripstone_block": "clay",
    "pointed_dripstone": "clay",
    "calcite": "snow",
    "tuff": "stone",
    "smooth_basalt": "gray",
    "raw_iron_block": "light_gray",
    "raw_gold_block": "gold",
    "raw_copper_block": "orange",
    "iron_block": "light_gray",
    "gold_block": "gold",
    "diamond_block": "diamond",
    "emerald_block": "emerald",
    "lapis_block": "lapis",
    "redstone_block": "fire",
    "netherite_block": "black",
    "ancient_debris": "black",
    "slime": "emerald",
    "honey_block": "gold",
    "honeycomb_block": "gold",
    "beehive": "wood",
    "bee_nest": "gold",
    "tnt": "red",
    "web": "snow",
    "wool": "snow",
    "carpet": "snow",
    "bed": "red",
    "cake": "snow",
    "composter": "wood",
    "scaffolding": "wood",
    "mob_spawner": "black",
    "end_portal_frame": "sand",
    "reeds": "plant",
    "waterlily": "plant",
    "seagrass": "plant",
    "kelp": "green",
    "turtle_egg": "sand",
    "frog_spawn": "plant",
    "amethyst_block": "purple",
    "budding_amethyst": "purple",
    "chiseled_bookshelf": "wood",
    "lodestone": "light_gray",
    "respawn_anchor": "purple",
    "target": "red",
    "lightning_rod": "orange",
}

# Matched in order against a block id when the exact list above misses it. First hit wins, so the
# specific needles come before the general ones: red_sandstone before sand, nether_brick before brick.
KEYWORDS: list[tuple[str, str]] = [
    ("water", "water"),
    ("lava", "fire"),
    ("blue_ice", "ice"),
    ("ice", "ice"),
    ("snow", "snow"),
    ("leaves", "plant"),
    ("mushroom_block", "brown"),
    ("mushroom_stem", "snow"),
    ("nether_brick", "black"),
    ("nether_wart", "nether"),
    ("nether_gold", "nether"),
    ("nether_sprouts", "warped"),
    ("netherrack", "nether"),
    ("warped", "warped"),
    ("crimson", "crimson"),
    ("weeping_vines", "crimson"),
    ("twisting_vines", "warped"),
    ("soul", "dark_wood"),
    ("blackstone", "black"),
    ("basalt", "gray"),
    ("deepslate", "deepslate"),
    ("quartz", "snow"),
    ("purpur", "purple"),
    ("end_stone", "sand"),
    ("end_rod", "snow"),
    ("chorus", "purple"),
    ("obsidian", "black"),
    ("amethyst", "purple"),
    ("copper", "orange"),
    ("coal", "black"),
    ("iron", "light_gray"),
    ("gold", "gold"),
    ("diamond", "diamond"),
    ("emerald", "emerald"),
    ("lapis", "lapis"),
    ("redstone", "fire"),
    ("prismarine", "warped"),
    ("sea_lantern", "diamond"),
    ("glowstone", "gold"),
    ("red_sandstone", "orange"),
    ("red_sand", "orange"),
    ("sandstone", "sand"),
    ("sand", "sand"),
    ("gravel", "light_gray"),
    ("terracotta", "clay"),
    ("clay", "clay"),
    ("brick", "red"),
    ("moss", "plant"),
    ("mud", "dark_wood"),
    ("farmland", "dirt"),
    ("wheat", "plant"),
    ("carrot", "plant"),
    ("potato", "plant"),
    ("beetroot", "plant"),
    ("pitcher", "plant"),
    ("torchflower", "plant"),
    ("vine", "plant"),
    ("sapling", "plant"),
    ("propagule", "plant"),
    ("flower", "plant"),
    ("tulip", "plant"),
    ("orchid", "plant"),
    ("allium", "plant"),
    ("bluet", "plant"),
    ("daisy", "plant"),
    ("poppy", "plant"),
    ("dandelion", "plant"),
    ("cornflower", "plant"),
    ("lilac", "plant"),
    ("peony", "plant"),
    ("rose", "plant"),
    ("bush", "plant"),
    ("grass", "plant"),
    ("glass", "light_gray"),
    ("log", "wood"),
    ("stem", "wood"),
    ("wood", "wood"),
    ("planks", "wood"),
    ("fence", "wood"),
    ("door", "wood"),
    ("sign", "wood"),
    ("bamboo", "plant"),
    ("cobble", "stone"),
    ("andesite", "stone"),
    ("diorite", "snow"),
    ("granite", "dirt"),
    ("stone", "stone"),
    ("dirt", "dirt"),
    ("concrete", "light_gray"),
    ("wool", "snow"),
    ("carpet", "snow"),
    ("slime", "emerald"),
    ("honey", "gold"),
    ("rail", "light_gray"),
    ("anvil", "light_gray"),
    ("cauldron", "gray"),
    ("furnace", "stone"),
    ("piston", "wood"),
    ("observer", "stone"),
    ("dispenser", "stone"),
    ("dropper", "stone"),
    ("hopper", "gray"),
    ("chest", "wood"),
    ("banner", "snow"),
    ("candle", "snow"),
    ("shulker_box", "purple"),
    ("bed", "red"),
    ("lantern", "gold"),
    ("fire", "orange"),
    ("barrier", "red"),
    ("structure_void", "unknown"),
]

# A dye word in an id colours the block, but only when the id also names something that comes dyed.
# Without that second test red_sand would come out dye red and blue_ice dye blue.
DYES = ("white", "orange", "magenta", "light_blue", "yellow", "lime", "pink", "light_gray", "gray",
        "cyan", "purple", "blue", "brown", "green", "red", "black")
DYED = ("wool", "carpet", "concrete", "terracotta", "glazed", "stained_glass", "glass_pane", "bed",
        "banner", "shulker_box", "candle", "mushroom", "dye", "wall_banner", "bundle")

# The player's arrow and the compass letters, drawn over the cells by images of their own.
ARROWS = ("n", "ne", "e", "se", "s", "sw", "w", "nw")
LETTERS = ("N", "E", "S", "W")
LETTER_PIXELS = {
    "N": ("10001", "11001", "10101", "10011", "10001"),
    "E": ("11111", "10000", "11110", "10000", "11111"),
    "S": ("01111", "10000", "01110", "00001", "11110"),
    "W": ("10001", "10001", "10101", "11011", "01010"),
}
# a waypoint's colour as the menu offers it, and the map colour it is drawn in
WAYPOINT_COLOURS = {"red": "fire", "orange": "orange", "yellow": "gold", "green": "emerald", "aqua": "diamond",
                    "blue": "lapis", "purple": "purple", "pink": "pink", "white": "snow"}
ARROW_COLOUR = (222, 46, 38)     # Xaero's minimap draws the player as a red arrow
OUTLINE = (20, 20, 24)           # the dark edge round the arrow and the letters, so they read on any ground
LETTER_COLOUR = (255, 255, 255)


def resolved() -> dict[str, str]:
    """Every colour name the block lists use, pointing at one of the colours that exist."""
    names = {name: name for name in COLOURS}
    names.update(ALIASES)
    return names


def shaded(colour: tuple[int, int, int], step: float) -> tuple[int, int, int, int]:
    return (*(min(255, round(channel * step)) for channel in colour), 255)


def values() -> list[tuple[int, int, int, int]]:
    """Every value a map cell can take: each colour at each brightness step, in index order."""
    return [shaded(colour, step) for colour in COLOURS.values() for step in SHADES]


def cell(value: tuple[int, int, int, int]) -> Image.Image:
    return Image.new("RGBA", (1, 1), value)


def arrow(direction: str) -> Image.Image:
    """The player's arrow, red with a dark edge on nothing, pointing one of eight ways."""
    scale = 8
    size = MARKER * scale
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    # a triangle pointing up, as fractions of the square, then turned to face the direction
    # kept within 0.4 of the middle, so turning it by 45 degrees does not push a corner off the square
    points = [(0.5, 0.1), (0.75, 0.8), (0.5, 0.7), (0.25, 0.8)]
    turns = {"n": 0, "ne": 45, "e": 90, "se": 135, "s": 180, "sw": 225, "w": 270, "nw": 315}
    angle = math.radians(turns[direction])
    turned = []
    for px, py in points:
        dx, dy = px - 0.5, py - 0.5
        # screen y grows downward, so this sign pair turns the arrow clockwise on screen
        rx = dx * math.cos(angle) - dy * math.sin(angle)
        ry = dx * math.sin(angle) + dy * math.cos(angle)
        turned.append(((0.5 + rx) * size, (0.5 + ry) * size))
    draw.polygon(turned, fill=(*ARROW_COLOUR, 255))
    small = image.resize((MARKER, MARKER), Image.BOX)
    # the HUD draws this a few screen pixels across, where a soft edge reads as a smudge, so take the
    # shrunk shape back to hard pixels (every pixel more than half covered becomes arrow) and edge it
    return outlined({(x, y) for y in range(MARKER) for x in range(MARKER) if small.getpixel((x, y))[3] > 127},
                    MARKER, MARKER, ARROW_COLOUR)


def outlined(lit: set, width: int, height: int, colour: tuple) -> Image.Image:
    """The lit pixels in colour, each pixel touching one (diagonals too) in OUTLINE, the rest clear."""
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for x, y in lit:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if 0 <= x + dx < width and 0 <= y + dy < height and (x + dx, y + dy) not in lit:
                    image.putpixel((x + dx, y + dy), (*OUTLINE, 255))
    for x, y in lit:
        image.putpixel((x, y), (*colour, 255))
    return image


def letter(character: str) -> Image.Image:
    """A compass letter, its five by five pixels white with a dark edge, on a clear seven by seven square."""
    rows = LETTER_PIXELS[character]
    lit = {(column + 1, row + 1) for row, bits in enumerate(rows) for column, bit in enumerate(bits) if bit == "1"}
    return outlined(lit, len(rows[0]) + 2, len(rows) + 2, LETTER_COLOUR)


def code(value: int) -> str:
    """A value's two letters: its two hex digits, each written a to p, so no slice of a title is a number."""
    return "".join(chr(ord("a") + int(digit, 16)) for digit in f"{value:02x}")


def textures() -> dict[str, Image.Image]:
    """Every texture the HUD names, by file name."""
    clear = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    files = {"c.png": clear, "czz.png": clear}
    for number, value in enumerate(values()):
        files[f"c{code(number)}.png"] = cell(value)
    for number, direction in enumerate(ARROWS):
        files[f"arrow{number}.png"] = arrow(direction)
    for number, character in enumerate(LETTERS):
        files[f"letter{number}.png"] = letter(character)
    return files


def palette_js() -> bytes:
    """The colour table for the script: block id to colour, with the rules it needs to guess."""
    names = list(COLOURS)
    index = {name: position for position, name in enumerate(names)}
    lookup = resolved()
    missing = sorted({colour for colour in list(BLOCKS.values()) + [c for _, c in KEYWORDS]
                      if lookup.get(colour) not in index})
    if missing:
        raise SystemExit(f"named colours that do not exist and are not aliases: {', '.join(missing)}")
    count = len(names) * len(SHADES)
    if count > MAX_VALUES:
        raise SystemExit(f"{count} values do not fit in two hex digits")
    blocks = {f"minecraft:{block}": index[lookup[colour]] for block, colour in BLOCKS.items()}
    dumped_blocks = json.dumps(blocks, indent="\t", sort_keys=True)
    dumped_dyes = json.dumps({dye: index[lookup.get(dye, dye)] for dye in DYES}, indent="\t")
    dumped_dyed = json.dumps(list(DYED), indent="\t")
    lines = [
        "// Generated by tools/palette.py. Do not edit: run the tool.",
        "//",
        "// A map cell's value is colour * SHADES + brightness step, the darker step first. The map title",
        "// names each cell's value in two lower case letters, its hex digits written a to p, which is",
        "// its texture's name in the resource pack: textures/ui/minimap/caa.png and on.",
        "",
        f"export const SHADES = {len(SHADES)};",
        f"export const VALUES = {count};",
        f"export const ARROWS = {len(ARROWS)};",
        "",
        f"export const UNKNOWN = {index['unknown']};",
        f"export const BORDER = {index['border']};",
        f"export const HOSTILE = {index['fire']};",
        f"export const PASSIVE = {index['snow']};",
        f"export const PLAYER = {index['diamond']};",
        f"export const ITEM = {index['gold']};",
        f"export const DEATH = {index['black']};",
        "",
        "// The colours a waypoint can be, as the menu names them.",
        "export const WAYPOINT_COLOURS = " + json.dumps({name: index[colour] for name, colour in WAYPOINT_COLOURS.items()},
                                                    indent="	") + ";",
        "",
        "// Every block whose colour is not a guess from its name.",
        f"export const BLOCKS = {dumped_blocks};",
        "",
        "// Tried in order against the rest of a block id. First hit wins.",
        "export const KEYWORDS = [",
        *(f'\t["{needle}", {index[lookup[colour]]}],' for needle, colour in KEYWORDS),
        "];",
        "",
        "// A dye word colours a block only when the id also names something that comes dyed.",
        f"export const DYES = {dumped_dyes};",
        f"export const DYED = {dumped_dyed};",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, "PNG", optimize=True)
    return buffer.getvalue()



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

def written(path: str, data: bytes, check: bool) -> bool:
    """True when the file on disk already holds this, so --check can tell and a write can be skipped."""
    current = same(path, data)
    if check or current:
        return current
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(data)
    return current


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="report whether the written files are up to date")
    args = parser.parse_args()

    files = {os.path.join(TEXTURES, name): png(image) for name, image in textures().items()}
    files[os.path.join(SCRIPTS, "palette.js")] = palette_js()

    # a texture left over from a palette that had more colours would still ship in the pack
    spare = [name for name in sorted(os.listdir(TEXTURES))
             if os.path.join(TEXTURES, name) not in files] if os.path.isdir(TEXTURES) else []
    for name in spare:
        print(f"{'stale' if args.check else 'removed'} {name}, which this palette does not use")
        if not args.check:
            os.remove(os.path.join(TEXTURES, name))

    stale = [path for path, data in files.items() if not written(path, data, args.check)]
    print(f"{len(COLOURS)} colours x {len(SHADES)} steps = {len(COLOURS) * len(SHADES)} values, "
          f"{len(files) - 1} textures")
    for path in sorted(stale):
        print(f"stale {os.path.relpath(path, ROOT)}")
    if args.check:
        return 1 if stale or spare else 0
    print(f"{len(stale)} of {len(files)} files written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
