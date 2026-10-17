"""Writes the HUD layer the map is drawn on, and the title layout the script fills it from.

An add-on cannot draw on the screen, but a resource pack can add controls to the HUD, and a HUD control
can read the title text. So the script sends the map as a title, the HUD keeps the last one (the
preserved-title pattern, as cobblemon-bedrock's party does) and hides the vanilla title for it, and a
grid of image controls, one per map cell, each slices its two characters out of that title and shows
the texture they name. That is a map of real pixels: square, any size, with no gap between cells.

    development_resource_packs/minimap/ui/hud_screen.json       the map layer, added to the HUD
    development_behavior_packs/minimap/scripts/hud_layout.js    where each field of the title sits

    python tools/hud.py            # write them
    python tools/hud.py --check    # exit 1 if either is out of date

A title is at most 512 characters (the server refuses a longer one with "Invalid message length"), and a
map 40 cells across is over 3,500, so the map goes as several titles: one header and a title per CHUNK
rows. Each kind of title starts with its own marker, and the HUD keeps each in a data control of its
own, which copies a title over only when one with its marker arrives. The script sends one title a tick
and only those that changed.

The titles are fixed width, because JSON UI can only cut a string at a byte count it is given: '%.Ns'
keeps the first N bytes, and taking one prefix away from a longer one leaves the bytes between.

    header      mm:maph, then
                    S             which of SIZES the map is, or "x" for no map (a lone "-" reads as 0)
                    A             which of the eight arrows the player is
                    LLLL          which compass letter sits in the top, right, bottom and left edges
                    VVVVV         for each of the INFO lines below, S again when the line is on and "x"
                                  when it is not, so a line's label needs one comparison, like the arrow's
                                  (JSON UI did not honour "and" over two slices)
                    info          INFO lines of INFO_WIDTH bytes, shown under the map in order (render.js
                                  fills them with whichever of the coordinates, camera angle, biome, light
                                  and time are on)
    row chunk   mm:maprNN (NN the chunk, two digits), then up to CHUNK rows of the map with its frame,
                top first, each COLUMNS cells of two hex digits, the right-hand cell first, so the map
                grows out of the corner it is anchored to. A cell past the map's edge is "zz", a
                transparent texture, and a row the map does not reach is not sent: its slice comes out
                empty and "c" is transparent too. A chunk the map does not reach is sent with no rows.

Each row control cuts its row out of its chunk once, and its cells cut from the row, so no cell works
on the whole title every frame.
"""

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "development_resource_packs", "minimap", "ui", "hud_screen.json")
LAYOUT = os.path.join(ROOT, "development_behavior_packs", "minimap", "scripts", "hud_layout.js")

MARKER = "mm:map"
SIZES = [8, 12, 16, 20, 24, 32, 40]   # cells across, inside the frame
COLUMNS = max(SIZES) + 2              # cells in a row of the title, frame included
INFO = 5                              # lines of text under the map, as Xaero's minimap shows
INFO_WIDTH = 28                       # bytes of each
INFO_FONT = 0.5                       # of the game's font, which is as tall as a 36 unit map at full size
INFO_LINE = 5                         # GUI units a line takes
CELL = 2                              # GUI units a cell is across; a whole number keeps every cell the same size
MARGIN = 4                            # GUI units from the top right corner of the screen
ARROW = 6                             # GUI units across the player's arrow
LETTER = 5                            # GUI units across a compass letter
TEXTURES = "textures/ui/minimap/"
NO_CELL = "zz"

HEAD_MARKER = MARKER + "h"
CHUNK = 5                             # map rows in one title: 9 + 5 * 84 bytes, inside the 512 a title may be
CHUNKS = -(-COLUMNS // CHUNK)
FIELD_SIZE = len(HEAD_MARKER)
FIELD_ARROW = FIELD_SIZE + 1
FIELD_LETTER = FIELD_ARROW + 1          # four of them: top, right, bottom, left
FIELD_SHOWN = FIELD_LETTER + 4
FIELD_INFO = FIELD_SHOWN + INFO
HEADER = FIELD_INFO + INFO * INFO_WIDTH
ROW = COLUMNS * 2


def chunk_marker(chunk: int) -> str:
    return f"{MARKER}r{chunk:02d}"


CHUNK_HEAD = len(chunk_marker(0))
assert CHUNK_HEAD + CHUNK * ROW <= 512 and HEADER <= 512, "a title would be longer than the 512 a title may be"


def field(start: int, length: int, source: str = "#preserved_text") -> str:
    """The bytes from start to start + length of a string, as a JSON UI expression."""
    if start == 0:
        return f"('%.{length}s' * {source})"
    return f"(('%.{start + length}s' * {source}) - ('%.{start}s' * {source}))"


def from_data(expression: str, target: str, source: str = "minimap_data") -> dict:
    return {
        "binding_type": "view",
        "source_control_name": source,
        "resolve_sibling_scope": True,
        "source_property_name": expression,
        "target_property_name": target,
    }


def showing(size: int) -> str:
    # a one-digit slice comes out of JSON UI as a number, so it is compared with one
    return f"({field(FIELD_SIZE, 1)} = {SIZES.index(size)})"


def data_control(name: str = "minimap_data", marker: str = HEAD_MARKER) -> dict:
    # the title is only there for a moment; this keeps the last title with its marker until the next one,
    # and is visible only for the frame a new one arrives, which is when visibility_changed copies it over
    return {name: {
        "type": "panel",
        "size": [0, 0],
        "property_bag": {"#preserved_text": ""},
        "bindings": [
            {"binding_name": "#hud_title_text_string"},
            {"binding_name": "#hud_title_text_string", "binding_name_override": "#preserved_text",
             "binding_condition": "visibility_changed"},
            {"binding_type": "view",
             "source_property_name": f"(not (#hud_title_text_string = #preserved_text) and not "
                                     f"((#hud_title_text_string - '{marker}') = #hud_title_text_string))",
             "target_property_name": "#visible"},
        ],
    }}


def row_control(row: int) -> dict:
    return {f"minimap_r{row}": {
        "type": "panel",
        "size": [0, 0],
        "property_bag": {"#row": "r"},
        # "r" in front, so a cell's prefix starts with a byte the row never repeats. '-' takes away every
        # copy of what it is given, and without it the second cell's two bytes taken off the first four
        # would also take the second cell whenever it matched the first.
        "bindings": [from_data(f"('r' + {field(CHUNK_HEAD + (row % CHUNK) * ROW, ROW)})", "#row",
                               f"minimap_k{row // CHUNK}")],
    }}


def cell_control(row: int, column: int) -> dict:
    """The cell `column` places in from the right-hand edge of the frame, `row` down from the top."""
    return {f"minimap_c{row}_{column}": {
        "type": "image",
        "size": [CELL, CELL],
        "anchor_from": "top_right",
        "anchor_to": "top_right",
        "offset": [-column * CELL, row * CELL],
        "layer": 1,
        "texture": f"{TEXTURES}c",
        "bindings": [{
            "binding_type": "view",
            "source_control_name": f"minimap_r{row}",
            "resolve_sibling_scope": True,
            "source_property_name": f"('{TEXTURES}c' + {field(column * 2 + 1, 2, '#row')})",
            "target_property_name": "#texture",
        }],
    }}


def marker_controls(size: int) -> list[dict]:
    """The arrow in the middle, a compass letter in each edge and the lines of text under the map, at this size."""
    span = (size + 2) * CELL
    middle = span / 2
    return [
        {f"minimap_arrow_{size}": {
            "type": "image",
            "size": [ARROW, ARROW],
            "anchor_from": "top_right",
            "anchor_to": "top_right",
            "offset": [-(middle - ARROW / 2), middle - ARROW / 2],
            "layer": 2,
            "texture": f"{TEXTURES}arrow0",
            "bindings": [
                from_data(f"('{TEXTURES}arrow' + {field(FIELD_ARROW, 1)})", "#texture"),
                from_data(showing(size), "#visible"),
            ],
        }},
    ] + [
        {f"minimap_letter_{size}_{edge}": {
            "type": "image",
            "size": [LETTER, LETTER],
            "anchor_from": "top_right",
            "anchor_to": "top_right",
            "offset": [-(at_x - LETTER / 2), at_y - LETTER / 2],
            "layer": 2,
            "texture": f"{TEXTURES}letter{edge}",
            "bindings": [
                from_data(f"('{TEXTURES}letter' + {field(FIELD_LETTER + edge, 1)})", "#texture"),
                from_data(showing(size), "#visible"),
            ],
        }}
        # the middle of each edge of the frame, top, right, bottom, left, measured from the top right corner
        for edge, (at_x, at_y) in enumerate([(middle, CELL / 2), (CELL / 2, middle), (middle, span - CELL / 2), (span - CELL / 2, middle)])
    ] + [
        {f"minimap_info_{size}_{line}": {
            "type": "label",
            "size": [160, INFO_LINE],
            "anchor_from": "top_right",
            "anchor_to": "top_right",
            "offset": [0, span + 1 + line * INFO_LINE],
            "font_scale_factor": INFO_FONT,
            "layer": 2,
            "shadow": True,
            "text_alignment": "right",
            "text": "#text",
            "bindings": [
                from_data(field(FIELD_INFO + line * INFO_WIDTH, INFO_WIDTH), "#text"),
                from_data(f"({field(FIELD_SHOWN + line, 1)} = {SIZES.index(size)})", "#visible"),
            ],
        }}
        for line in range(INFO)
    ]


def hud() -> dict:
    controls = [data_control()] + [data_control(f"minimap_k{chunk}", chunk_marker(chunk)) for chunk in range(CHUNKS)]
    controls += [row_control(row) for row in range(COLUMNS)]
    controls += [cell_control(row, column) for row in range(COLUMNS) for column in range(COLUMNS)]
    for size in SIZES:
        controls += marker_controls(size)
    # Both this pack and cobblemon-bedrock hide the vanilla title for their own titles, by a #visible
    # binding each adds to hud_title_text, and the binding added last decides. So each hides the
    # other's titles too, and either pack can sit on top.
    hidden = " and ".join(f"((#hud_title_text_string - '{marker}') = #hud_title_text_string)"
                          for marker in (MARKER, "cbm:party", "cbm:scan", "cbm:ride", "cbm:toast"))
    return {
        "namespace": "hud",
        "root_panel": {"modifications": [{
            "array_name": "controls",
            "operation": "insert_back",
            "value": {"minimap@hud.minimap": {}},
        }]},
        "hud_title_text": {"modifications": [{
            "array_name": "bindings",
            "operation": "insert_back",
            "value": [
                {"binding_name": "#hud_title_text_string", "binding_type": "global"},
                {"binding_type": "view", "source_property_name": f"({hidden})", "target_property_name": "#visible"},
            ],
        }]},
        "minimap": {
            "type": "panel",
            "size": ["100%", "100%"],
            "controls": [{"minimap_map": {
                "type": "panel",
                "size": [COLUMNS * CELL, COLUMNS * CELL + 2 + INFO * INFO_LINE],
                "anchor_from": "top_right",
                "anchor_to": "top_right",
                "offset": [-MARGIN, MARGIN],
                "controls": controls,
            }}],
        },
    }


def layout_js() -> str:
    lines = [
        "// Generated by tools/hud.py. Do not edit: run the tool.",
        "//",
        "// Where each field of the map title sits, which ui/hud_screen.json in the resource pack cuts",
        "// out by byte count. See tools/hud.py for the whole layout.",
        "",
        f'export const MARKER = "{MARKER}";',
        f"export const SIZES = {json.dumps(SIZES)};",
        f"export const COLUMNS = {COLUMNS};",
        f"export const INFO = {INFO};",
        f"export const INFO_WIDTH = {INFO_WIDTH};",
        f'export const HEAD_MARKER = "{HEAD_MARKER}";',
        f"export const CHUNK = {CHUNK};",
        f"export const CHUNKS = {CHUNKS};",
        f'export const NO_CELL = "{NO_CELL}";',
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="report whether the written files are up to date")
    args = parser.parse_args()
    # one line: it is nearly two thousand controls, and nobody reads it by hand
    files = {UI: json.dumps(hud(), separators=(",", ":")) + "\n", LAYOUT: layout_js()}
    stale = []
    for path, text in files.items():
        current = os.path.exists(path) and open(path, encoding="utf-8").read() == text
        if current:
            continue
        stale.append(path)
        if not args.check:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
    for path in stale:
        print(f"{'stale' if args.check else 'wrote'} {os.path.relpath(path, ROOT)}")
    return 1 if args.check and stale else 0


if __name__ == "__main__":
    sys.exit(main())
