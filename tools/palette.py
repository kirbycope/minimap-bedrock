"""Writes the minimap's glyph pages and the colour table the behaviour pack reads.

Bedrock has no way to draw pixels on the HUD, so the map is text: characters from a font this pack
brings with it. Two measurements, both taken in the game and both out of a pack's hands, set everything
else:

    a line of text is ten pixels tall, whatever is written on it
    a glyph takes the width of the pixels it actually has, plus one

That ten is the floor on how fine the map can be, so a glyph carries TWO map pixels, stacked, five
pixels each. Four pixels of art plus the one Minecraft adds makes a column five across as well, so the
map comes out square at five pixels a block: four times the map in the same corner as one pixel to a
glyph would give. It is the idea behind drawing with braille dots in a terminal, except that this pack
supplies its own font, so each half is a full colour rather than a dot that is on or off.

The price is combinations. A glyph has to exist for every pair of values that can sit one above the
other, so N values need N squared glyphs, and the private use area holds 6400 characters, 25 pages of
256. Thirty-two colours in two brightness steps is 64 values, 4096 glyphs and 16 pages, which leaves a
page over for the player's arrow and the compass letters.

    development_resource_packs/minimap/font/glyph_E0.png        the arrow and the letters
    development_resource_packs/minimap/font/glyph_E1..F0.png    every pair of terrain values
    development_behavior_packs/minimap/scripts/palette.js       block id -> colour, for the script

    python tools/palette.py            # write them
    python tools/palette.py --check    # exit 1 if any is out of date

The terrain pages are contiguous from U+E100, so a pair's character is simply U+E100 plus top * 64 plus
bottom, and no page arithmetic appears anywhere in the script.
"""

import argparse
import io
import json
import math
import os
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT = os.path.join(ROOT, "development_resource_packs", "minimap", "font")
SCRIPTS = os.path.join(ROOT, "development_behavior_packs", "minimap", "scripts")

# A page's cells are square, sized by the page's width over sixteen, so the cell has to be as tall as a
# line of text and the art simply does not fill it across.
CELL = 10           # the square cell a glyph is cut from, as tall as a line of text
CELL_W = 4          # pixels of art across it; Minecraft adds one, so a map pixel is five wide
CELL_H = 10         # pixels of art down it, holding two map pixels of five
GRID = 16           # cells per row in a page, so 256 glyphs a page
SHADES = (0.71, 1.0)    # a cell takes the darker step when it is lower than the cell to its north
OVERLAY_PAGE = 0xE0
TERRAIN_PAGE = 0xE1

# Minecraft's own map colours, the ones the map in your hand is drawn with. Thirty-two of them, because
# every pair of values needs a glyph of its own and that is what fits in the private use area.
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

# Page E0. The player's arrow and the compass letters are two glyphs side by side, so they are eight
# pixels across rather than four, which is enough to read.
ARROWS = ("n", "ne", "e", "se", "s", "sw", "w", "nw")
LETTERS = ("N", "E", "S", "W")
LETTER_PIXELS = {
    "N": ("10001", "11001", "10101", "10011", "10001"),
    "E": ("11111", "10000", "11110", "10000", "11111"),
    "S": ("01111", "10000", "01110", "00001", "11110"),
    "W": ("10001", "10001", "10101", "11011", "01010"),
}
ARROW_COLOUR = (255, 255, 255)
ARROW_BACK = (24, 24, 28)
LETTER_COLOUR = (240, 240, 240)


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


def terrain_pages() -> list[Image.Image]:
    """A glyph for every pair of values, top half over bottom half, 256 to a page."""
    palette = values()
    half = CELL_H // 2
    pages = []
    for first in range(0, len(palette) ** 2, GRID * GRID):
        page = Image.new("RGBA", (CELL * GRID, CELL * GRID), (0, 0, 0, 0))
        draw = ImageDraw.Draw(page)
        for cell in range(GRID * GRID):
            pair = first + cell
            x, y = (cell % GRID) * CELL, (cell // GRID) * CELL
            # a pixel is left clear under each half, so the line Minecraft puts between characters has
            # its match between the rows and the grid over the map is even on all four sides
            for value, offset in ((pair // len(palette), 0), (pair % len(palette), half)):
                draw.rectangle((x, y + offset, x + CELL_W - 1, y + offset + half - 2), fill=palette[value])
        pages.append(page)
    return pages


def arrow(direction: str) -> Image.Image:
    """One arrow, eight pixels across and ten down, to be cut into two glyphs."""
    scale = 8
    width, height = CELL_W * 2 * scale, CELL_H * scale
    image = Image.new("RGBA", (width, height), (*ARROW_BACK, 255))
    draw = ImageDraw.Draw(image)
    # a triangle pointing up, as fractions of the cell, then turned to face the direction; a notched
    # arrowhead was tried first and eight pixels across is not enough to hold the notch
    points = [(0.5, 0.06), (0.94, 0.94), (0.06, 0.94)]
    turns = {"n": 0, "ne": 45, "e": 90, "se": 135, "s": 180, "sw": 225, "w": 270, "nw": 315}
    angle = math.radians(turns[direction])
    turned = []
    for px, py in points:
        dx, dy = px - 0.5, py - 0.5
        # screen y grows downward, so this sign pair turns the arrow clockwise on screen
        rx = dx * math.cos(angle) - dy * math.sin(angle)
        ry = dx * math.sin(angle) + dy * math.cos(angle)
        turned.append(((0.5 + rx) * width, (0.5 + ry) * height))
    draw.polygon(turned, fill=(*ARROW_COLOUR, 255))
    small = image.resize((CELL_W * 2, CELL_H), Image.LANCZOS)
    # eight pixels across is too few for a soft edge to read as an arrow, so take the shrunk shape back
    # to two colours: every pixel more than half covered becomes arrow, the rest backdrop
    for y in range(CELL_H):
        for x in range(CELL_W * 2):
            red, green, blue, _ = small.getpixel((x, y))
            lit = (red + green + blue) / 3 > (sum(ARROW_BACK) + sum(ARROW_COLOUR)) / 6
            small.putpixel((x, y), (*(ARROW_COLOUR if lit else ARROW_BACK), 255))
    return small


def letter(character: str) -> Image.Image:
    image = Image.new("RGBA", (CELL_W * 2, CELL_H), (*ARROW_BACK, 255))
    rows = LETTER_PIXELS[character]
    left, top = (CELL_W * 2 - len(rows[0])) // 2, (CELL_H - len(rows)) // 2
    for row, bits in enumerate(rows):
        for column, bit in enumerate(bits):
            if bit == "1":
                image.putpixel((left + column, top + row), (*LETTER_COLOUR, 255))
    return image


def overlay_page() -> Image.Image:
    """The arrows then the letters, each cut into its left half and its right half, left half first."""
    page = Image.new("RGBA", (CELL * GRID, CELL * GRID), (0, 0, 0, 0))
    wide = [arrow(direction) for direction in ARROWS] + [letter(character) for character in LETTERS]
    for index, image in enumerate(wide):
        for half in (0, 1):
            cell = index * 2 + half
            box = ((cell % GRID) * CELL, (cell // GRID) * CELL)
            page.paste(image.crop((half * CELL_W, 0, (half + 1) * CELL_W, CELL_H)), box)
    return page


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
    if count ** 2 > 25 * GRID * GRID:
        raise SystemExit(f"{count} values need {count ** 2} glyphs, more than the private use area holds")
    blocks = {f"minecraft:{block}": index[lookup[colour]] for block, colour in BLOCKS.items()}
    dumped_blocks = json.dumps(blocks, indent="\t", sort_keys=True)
    dumped_dyes = json.dumps({dye: index[lookup.get(dye, dye)] for dye in DYES}, indent="\t")
    dumped_dyed = json.dumps(list(DYED), indent="\t")
    lines = [
        "// Generated by tools/palette.py. Do not edit: run the tool.",
        "//",
        "// A map cell's value is colour * SHADES + brightness step, the darker step first. One character",
        "// of the map holds two cells, one above the other, and its code point is GLYPH_TERRAIN + top *",
        "// VALUES + bottom. The overlay page holds the player's arrow and the compass letters, each as a",
        "// left half and a right half, so a marker is two characters wide and one tall.",
        "",
        f"export const CELL_W = {CELL_W};",
        f"export const CELL_H = {CELL_H};",
        f"export const SHADES = {len(SHADES)};",
        f"export const VALUES = {count};",
        f"export const GLYPH_TERRAIN = 0x{TERRAIN_PAGE:02x}00;",
        f"export const GLYPH_OVERLAY = 0x{OVERLAY_PAGE:02x}00;",
        "export const ARROW = 0;",
        f"export const LETTER_N = {len(ARROWS) * 2};",
        "",
        f"export const UNKNOWN = {index['unknown']};",
        f"export const BORDER = {index['border']};",
        f"export const HOSTILE = {index['fire']};",
        f"export const PASSIVE = {index['snow']};",
        f"export const PLAYER = {index['diamond']};",
        f"export const ITEM = {index['gold']};",
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


def written(path: str, data: bytes, check: bool) -> bool:
    """True when the file on disk already holds this, so --check can tell and a write can be skipped."""
    current = os.path.exists(path) and open(path, "rb").read() == data
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

    files = {os.path.join(FONT, f"glyph_{OVERLAY_PAGE:02X}.png"): png(overlay_page())}
    for number, page in enumerate(terrain_pages()):
        files[os.path.join(FONT, f"glyph_{TERRAIN_PAGE + number:02X}.png")] = png(page)
    files[os.path.join(SCRIPTS, "palette.js")] = palette_js()

    # a page left over from a palette that had more colours would still be loaded by the game
    spare = [name for name in sorted(os.listdir(FONT)) if name.startswith("glyph_")
             and os.path.join(FONT, name) not in files] if os.path.isdir(FONT) else []
    for name in spare:
        print(f"{'stale' if args.check else 'removed'} {name}, which this palette does not use")
        if not args.check:
            os.remove(os.path.join(FONT, name))

    stale = [path for path, data in files.items() if not written(path, data, args.check)]
    print(f"{len(COLOURS)} colours x {len(SHADES)} steps = {len(COLOURS) * len(SHADES)} values, "
          f"{(len(COLOURS) * len(SHADES)) ** 2} glyphs over {len(files) - 1} pages")
    for path in sorted(stale):
        print(f"stale {os.path.relpath(path, ROOT)}")
    if args.check:
        return 1 if stale or spare else 0
    print(f"{len(stale)} of {len(files)} files written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
