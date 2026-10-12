"""Writes the minimap's glyph atlases and the colour table the behaviour pack reads.

Bedrock has no way to draw pixels on the HUD, so the map is text: one character per cell, drawn from a
custom font page where every glyph is a solid square of colour. This file is the only place the colours
live. It writes three files, and nothing else may be edited by hand:

    development_resource_packs/minimap/font/glyph_E1.png   terrain, 63 colours x 4 brightness steps
    development_resource_packs/minimap/font/glyph_E2.png   the player arrow, the compass letters
    development_behavior_packs/minimap/scripts/palette.js  block id -> colour, for the script

    python tools/palette.py            # write the three files
    python tools/palette.py --check    # exit 1 if any of them is out of date

A glyph page is a 16x16 grid of cells, so a page holds 256 characters: page E1 is U+E100 to U+E1FF and
page E2 is U+E200 to U+E2FF, both in the private use area, where nothing of Minecraft's own sits. The
cell is CELL pixels square and the art fills it completely, because Bedrock takes a glyph's width from
the art and a half-filled cell would leave a gap between map columns.

The four brightness steps are Minecraft's own map shading, which is what makes a map read as terrain
rather than as a colour field: a cell is drawn brighter than the cell to its north when it is higher,
darker when it is lower. Glyph index is colour * 4 + step, so the script finds a cell's character with
one addition.
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
CELL = 9        # pixels per glyph. A glyph draws one screen pixel per texture pixel, Minecraft puts one
                # pixel between characters that nothing in a pack can take out, and a line of text is ten
                # pixels tall whatever is on it. Nine is the size that puts the same one pixel line on every
                # side of a cell: an even grid, rather than stripes down the sides only, which is what a cell
                # of ten gives. It also makes the cell square, ten across by ten down.
GRID = 16       # cells per row in a page, so 256 glyphs
SHADES = (0.53, 0.71, 0.86, 1.0)    # Minecraft's own map brightness steps, darkest first

# Minecraft's own map colours, the ones the map in your hand is drawn with, so the minimap reads as
# that map rather than as a palette somebody picked. The order fixes each colour's index, so
# appending is safe and reordering is not.
COLOURS: dict[str, tuple[int, int, int]] = {
    "unknown": (58, 58, 64),
    "border": (124, 100, 78),
    "grass": (127, 178, 56),
    "plants": (0, 124, 0),
    "leaves": (0, 124, 0),
    "cactus": (0, 124, 0),
    "moss": (0, 124, 0),
    "dirt": (151, 109, 77),
    "podzol": (129, 86, 49),
    "mud": (76, 50, 35),
    "mycelium": (129, 86, 49),
    "sand": (247, 233, 163),
    "red_sand": (216, 127, 51),
    "gravel": (153, 153, 153),
    "clay": (164, 168, 184),
    "stone": (112, 112, 112),
    "deepslate": (100, 100, 100),
    "water": (64, 64, 255),
    "ice": (160, 160, 255),
    "snow": (255, 255, 255),
    "wood": (143, 119, 72),
    "dark_wood": (76, 50, 35),
    "bricks": (153, 51, 51),
    "glass": (199, 199, 199),
    "lava": (255, 0, 0),
    "magma": (112, 2, 0),
    "netherrack": (112, 2, 0),
    "nether_bricks": (76, 22, 22),
    "soul_soil": (76, 50, 35),
    "blackstone": (37, 22, 16),
    "warped": (22, 126, 134),
    "crimson": (189, 48, 49),
    "end_stone": (247, 233, 163),
    "purpur": (178, 76, 216),
    "obsidian": (25, 25, 25),
    "quartz": (255, 252, 245),
    "prismarine": (76, 127, 153),
    "glowstone": (229, 229, 51),
    "coal": (25, 25, 25),
    "iron": (216, 175, 147),
    "gold": (250, 238, 77),
    "diamond": (92, 219, 213),
    "emerald": (0, 217, 58),
    "lapis": (74, 128, 255),
    "redstone": (255, 0, 0),
    "copper": (216, 127, 51),
    "amethyst": (127, 63, 178),
    "white": (255, 255, 255),
    "orange": (216, 127, 51),
    "magenta": (178, 76, 216),
    "light_blue": (102, 153, 216),
    "yellow": (229, 229, 51),
    "lime": (127, 204, 25),
    "pink": (242, 127, 165),
    "gray": (76, 76, 76),
    "light_gray": (153, 153, 153),
    "cyan": (76, 127, 153),
    "purple": (127, 63, 178),
    "blue": (51, 76, 178),
    "brown": (102, 76, 51),
    "green": (102, 127, 51),
    "red": (153, 51, 51),
    "black": (25, 25, 25),
}

# A block whose colour its name does not give away.
BLOCKS: dict[str, str] = {
    "grass_block": "grass",
    "short_grass": "plants",
    "tall_grass": "plants",
    "fern": "plants",
    "large_fern": "plants",
    "dead_bush": "wood",
    "sugar_cane": "plants",
    "bamboo": "plants",
    "lily_pad": "leaves",
    "cactus": "cactus",
    "pumpkin": "orange",
    "carved_pumpkin": "orange",
    "lit_pumpkin": "orange",
    "melon_block": "green",
    "hay_block": "yellow",
    "dried_kelp_block": "green",
    "sponge": "yellow",
    "wet_sponge": "yellow",
    "coarse_dirt": "dirt",
    "rooted_dirt": "dirt",
    "dirt_with_roots": "dirt",
    "grass_path": "dirt",
    "podzol": "podzol",
    "mycelium": "mycelium",
    "mud": "mud",
    "packed_mud": "dirt",
    "soul_sand": "soul_soil",
    "magma": "magma",
    "shroomlight": "orange",
    "netherrack": "netherrack",
    "bedrock": "blackstone",
    "crying_obsidian": "purple",
    "chest": "wood",
    "crafting_table": "wood",
    "barrel": "wood",
    "bookshelf": "wood",
    "ladder": "wood",
    "torch": "yellow",
    "lantern": "gold",
    "soul_lantern": "warped",
    "campfire": "orange",
    "soul_campfire": "warped",
    "beacon": "diamond",
    "sculk": "blackstone",
    "sculk_catalyst": "blackstone",
    "sculk_sensor": "warped",
    "sculk_shrieker": "quartz",
    "bone_block": "quartz",
    "snow_layer": "snow",
    "powder_snow": "snow",
    "frosted_ice": "ice",
    "blue_ice": "ice",
    "packed_ice": "ice",
    "mangrove_roots": "dark_wood",
    "muddy_mangrove_roots": "mud",
    "moss_block": "moss",
    "moss_carpet": "moss",
    "pale_moss_block": "light_gray",
    "pale_hanging_moss": "light_gray",
    "azalea_leaves": "leaves",
    "azalea_leaves_flowered": "pink",
    "big_dripleaf": "plants",
    "small_dripleaf_block": "plants",
    "spore_blossom": "pink",
    "glow_lichen": "warped",
    "hanging_roots": "wood",
    "dripstone_block": "clay",
    "pointed_dripstone": "clay",
    "calcite": "quartz",
    "tuff": "stone",
    "smooth_basalt": "gray",
    "raw_iron_block": "iron",
    "raw_gold_block": "gold",
    "raw_copper_block": "copper",
    "iron_block": "light_gray",
    "gold_block": "gold",
    "diamond_block": "diamond",
    "emerald_block": "emerald",
    "lapis_block": "lapis",
    "redstone_block": "redstone",
    "netherite_block": "blackstone",
    "ancient_debris": "blackstone",
    "slime": "lime",
    "honey_block": "yellow",
    "honeycomb_block": "yellow",
    "beehive": "wood",
    "bee_nest": "yellow",
    "tnt": "red",
    "web": "white",
    "wool": "white",
    "carpet": "white",
    "bed": "red",
    "cake": "white",
    "composter": "wood",
    "scaffolding": "wood",
    "mob_spawner": "blackstone",
    "end_portal_frame": "end_stone",
    "reeds": "plants",
    "waterlily": "leaves",
    "seagrass": "leaves",
    "kelp": "green",
    "turtle_egg": "sand",
    "frog_spawn": "plants",
    "amethyst_block": "amethyst",
    "budding_amethyst": "amethyst",
    "chiseled_bookshelf": "wood",
    "lodestone": "light_gray",
    "respawn_anchor": "purple",
    "target": "red",
    "lightning_rod": "copper",
}

# Matched in order against a block id when the exact lists above miss it. First hit wins, so the
# specific needles come before the general ones: red_sandstone before sand, nether_brick before brick.
KEYWORDS: list[tuple[str, str]] = [
    ("water", "water"),
    ("lava", "lava"),
    ("blue_ice", "ice"),
    ("ice", "ice"),
    ("snow", "snow"),
    ("leaves", "leaves"),
    ("mushroom_block", "brown"),
    ("mushroom_stem", "quartz"),
    ("nether_brick", "nether_bricks"),
    ("nether_wart", "netherrack"),
    ("nether_gold", "netherrack"),
    ("nether_sprouts", "warped"),
    ("netherrack", "netherrack"),
    ("warped", "warped"),
    ("crimson", "crimson"),
    ("weeping_vines", "crimson"),
    ("twisting_vines", "warped"),
    ("soul", "soul_soil"),
    ("blackstone", "blackstone"),
    ("basalt", "gray"),
    ("deepslate", "deepslate"),
    ("quartz", "quartz"),
    ("purpur", "purpur"),
    ("end_stone", "end_stone"),
    ("end_rod", "quartz"),
    ("chorus", "purpur"),
    ("obsidian", "obsidian"),
    ("amethyst", "amethyst"),
    ("copper", "copper"),
    ("coal", "coal"),
    ("iron", "iron"),
    ("gold", "gold"),
    ("diamond", "diamond"),
    ("emerald", "emerald"),
    ("lapis", "lapis"),
    ("redstone", "redstone"),
    ("prismarine", "prismarine"),
    ("sea_lantern", "prismarine"),
    ("glowstone", "glowstone"),
    ("red_sandstone", "red_sand"),
    ("red_sand", "red_sand"),
    ("sandstone", "sand"),
    ("sand", "sand"),
    ("gravel", "gravel"),
    ("terracotta", "clay"),
    ("clay", "clay"),
    ("brick", "bricks"),
    ("moss", "moss"),
    ("mud", "mud"),
    ("farmland", "dirt"),
    ("wheat", "plants"),
    ("carrot", "plants"),
    ("potato", "plants"),
    ("beetroot", "plants"),
    ("pitcher", "plants"),
    ("torchflower", "plants"),
    ("vine", "leaves"),
    ("sapling", "leaves"),
    ("propagule", "leaves"),
    ("flower", "plants"),
    ("tulip", "plants"),
    ("orchid", "plants"),
    ("allium", "plants"),
    ("bluet", "plants"),
    ("daisy", "plants"),
    ("poppy", "plants"),
    ("dandelion", "plants"),
    ("cornflower", "plants"),
    ("lilac", "plants"),
    ("peony", "plants"),
    ("rose", "plants"),
    ("bush", "plants"),
    ("grass", "plants"),
    ("glass", "glass"),
    ("log", "wood"),
    ("stem", "wood"),
    ("wood", "wood"),
    ("planks", "wood"),
    ("fence", "wood"),
    ("door", "wood"),
    ("sign", "wood"),
    ("bamboo", "plants"),
    ("cobble", "stone"),
    ("andesite", "stone"),
    ("diorite", "quartz"),
    ("granite", "dirt"),
    ("stone", "stone"),
    ("dirt", "dirt"),
    ("concrete", "light_gray"),
    ("wool", "white"),
    ("carpet", "white"),
    ("slime", "lime"),
    ("honey", "yellow"),
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
    ("banner", "white"),
    ("candle", "white"),
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

# Page E2, in order. The player arrow points the way the player faces, in eight steps from north.
ARROWS = ("n", "ne", "e", "se", "s", "sw", "w", "nw")
LETTERS = ("N", "E", "S", "W")
# 5x5 pixel letters. Three pixels across was tried first and makes N and W mirror images of each other,
# which is no good on a compass.
LETTER_PIXELS = {
    "N": ("10001", "11001", "10101", "10011", "10001"),
    "E": ("11111", "10000", "11110", "10000", "11111"),
    "S": ("01111", "10000", "01110", "00001", "11110"),
    "W": ("10001", "10001", "10101", "11011", "01010"),
}
ARROW_COLOUR = (255, 255, 255)
ARROW_BACK = (24, 24, 28)
LETTER_COLOUR = (240, 240, 240)


def shaded(colour: tuple[int, int, int], step: float) -> tuple[int, int, int, int]:
    return (*(min(255, round(channel * step)) for channel in colour), 255)


def page_e1() -> Image.Image:
    """Terrain: colour * 4 + brightness step, so U+E100 + that is the character."""
    image = Image.new("RGBA", (CELL * GRID, CELL * GRID), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for index, colour in enumerate(COLOURS.values()):
        for step, factor in enumerate(SHADES):
            cell = index * len(SHADES) + step
            x, y = (cell % GRID) * CELL, (cell // GRID) * CELL
            draw.rectangle((x, y, x + CELL - 1, y + CELL - 1), fill=shaded(colour, factor))
    return image   # the glyphs past the last colour are left clear


def arrow(direction: str) -> Image.Image:
    """One arrow cell, drawn large and shrunk down so its edges are not a staircase."""
    scale = 8
    size = CELL * scale
    image = Image.new("RGBA", (size, size), (*ARROW_BACK, 255))
    draw = ImageDraw.Draw(image)
    # a triangle pointing up, as fractions of the cell, then turned to face the direction;
    # a notched arrowhead was tried first and eight pixels across is not enough to hold the notch
    points = [(0.5, 0.06), (0.94, 0.94), (0.06, 0.94)]
    turns = {"n": 0, "ne": 45, "e": 90, "se": 135, "s": 180, "sw": 225, "w": 270, "nw": 315}
    angle = math.radians(turns[direction])
    centre = 0.5
    turned = []
    for px, py in points:
        dx, dy = px - centre, py - centre
        # screen y grows downward, so a clockwise turn on screen is this sign pair
        rx = dx * math.cos(angle) - dy * math.sin(angle)
        ry = dx * math.sin(angle) + dy * math.cos(angle)
        turned.append(((centre + rx) * size, (centre + ry) * size))
    draw.polygon(turned, fill=(*ARROW_COLOUR, 255))
    small = image.resize((CELL, CELL), Image.LANCZOS)
    # eight pixels across is too few for a soft edge to read as an arrow, so take the shrunk shape
    # back to two colours: every pixel more than half covered becomes arrow, the rest backdrop
    for y in range(CELL):
        for x in range(CELL):
            red, green, blue, _ = small.getpixel((x, y))
            lit = (red + green + blue) / 3 > (sum(ARROW_BACK) + sum(ARROW_COLOUR)) / 6
            small.putpixel((x, y), (*(ARROW_COLOUR if lit else ARROW_BACK), 255))
    return small


def letter(character: str) -> Image.Image:
    image = Image.new("RGBA", (CELL, CELL), (*ARROW_BACK, 255))
    rows = LETTER_PIXELS[character]
    pixel = max(1, CELL // 9)   # the letters scale with the cell, whatever size it is set to
    width, height = len(rows[0]) * pixel, len(rows) * pixel
    left, top = (CELL - width) // 2, (CELL - height) // 2
    draw = ImageDraw.Draw(image)
    for row, bits in enumerate(rows):
        for column, bit in enumerate(bits):
            if bit == "1":
                x, y = left + column * pixel, top + row * pixel
                draw.rectangle((x, y, x + pixel - 1, y + pixel - 1), fill=(*LETTER_COLOUR, 255))
    return image


def page_e2() -> Image.Image:
    """Overlays: eight arrows, then the four compass letters."""
    image = Image.new("RGBA", (CELL * GRID, CELL * GRID), (0, 0, 0, 0))
    cells = [arrow(direction) for direction in ARROWS] + [letter(character) for character in LETTERS]
    for index, cell in enumerate(cells):
        image.paste(cell, ((index % GRID) * CELL, (index // GRID) * CELL))
    return image


def palette_js() -> bytes:
    """The colour table for the script: block id to colour index, with the rules it needs to guess."""
    names = list(COLOURS)
    index = {name: position for position, name in enumerate(names)}
    missing = sorted({colour for colour in BLOCKS.values() if colour not in index})
    if missing:
        raise SystemExit(f"BLOCKS names colours that do not exist: {', '.join(missing)}")
    unknown = sorted({colour for _, colour in KEYWORDS if colour not in index})
    if unknown:
        raise SystemExit(f"KEYWORDS names colours that do not exist: {', '.join(unknown)}")
    blocks = {f"minecraft:{block}": index[colour] for block, colour in BLOCKS.items()}
    dumped_blocks = json.dumps(blocks, indent="	", sort_keys=True)
    dumped_dyes = json.dumps({name: index[name] for name in DYES}, indent="	")
    dumped_dyed = json.dumps(list(DYED), indent="	")
    if len(names) * len(SHADES) > GRID * GRID:
        raise SystemExit(f"{len(names)} colours x {len(SHADES)} steps is more than the {GRID * GRID} glyphs in a page")
    lines = [
        "// Generated by tools/palette.py. Do not edit: run the tool.",
        "//",
        "// A cell's character is GLYPH_TERRAIN + colour * SHADES + brightness step, and the four steps run",
        "// darkest first. The overlay page holds the eight player arrows, then the compass letters N E S W.",
        "",
        f"export const CELL = {CELL};",
        f"export const SHADES = {len(SHADES)};",
        "export const GLYPH_TERRAIN = 0xe100;",
        "export const GLYPH_OVERLAY = 0xe200;",
        "export const ARROW = 0;",
        f"export const LETTER_N = {len(ARROWS)};",
        "",
        f"export const UNKNOWN = {index['unknown']};",
        f"export const BORDER = {index['border']};",
        f"export const WATER = {index['water']};",
        f"export const HOSTILE = {index['red']};",
        f"export const PASSIVE = {index['white']};",
        f"export const PLAYER = {index['light_blue']};",
        f"export const ITEM = {index['yellow']};",
        "",
        "// Every block whose colour is not a guess from its name.",
        f"export const BLOCKS = {dumped_blocks};",
        "",
        "// Tried in order against the rest of a block id. First hit wins.",
        "export const KEYWORDS = [",
        *(f'\t["{needle}", {index[colour]}],' for needle, colour in KEYWORDS),
        "];",
        "",
        "// A dye word colours a block only when the id also names something that comes dyed.",
        f"export const DYES = {dumped_dyes};",
        f"export const DYED = {dumped_dyed};",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def written(path: str, data: bytes, check: bool) -> bool:
    """True when the file on disk already holds this, so --check can tell and a write can be skipped."""
    current = os.path.exists(path) and open(path, "rb").read() == data
    if check or current:
        return current
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(data)
    return current


def png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, "PNG", optimize=True)
    return buffer.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="report whether the written files are up to date")
    args = parser.parse_args()

    files = {
        os.path.join(FONT, "glyph_E1.png"): png(page_e1()),
        os.path.join(FONT, "glyph_E2.png"): png(page_e2()),
        os.path.join(SCRIPTS, "palette.js"): palette_js(),
    }
    stale = [path for path, data in files.items() if not written(path, data, args.check)]
    for path in sorted(files):
        print(f"{'stale' if path in stale else 'ok   '} {os.path.relpath(path, ROOT)}")
    print(f"{len(COLOURS)} colours x {len(SHADES)} steps = {len(COLOURS) * len(SHADES)} of {GRID * GRID} glyphs")
    if args.check:
        return 1 if stale else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
