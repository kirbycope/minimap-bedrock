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

The title is fixed width, because JSON UI can only cut a string at a byte count it is given: '%.Ns'
keeps the first N bytes, and taking one prefix away from a longer one leaves the bytes between.

    mm:map        the marker, so a title from anywhere else leaves the map alone
    S             which of SIZES the map is, or "-" for no map
    A             which of the eight arrows the player is
    L             which compass letter sits in the top edge
    C             "y" when the coordinates are shown
    coordinates   COORDS bytes, padded on the left
    rows          one per row of the map with its frame, top first, each COLUMNS cells of two hex digits,
                  the right-hand cell first, so the map grows out of the corner it is anchored to. A
                  cell past the map's edge is "zz", a transparent texture, and a row the map does not
                  reach is not sent: its slice comes out empty and "c" is transparent too.

Each row control cuts its row out of the title once, and its cells cut from the row, so no cell works
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
COORDS = 28                           # bytes of the coordinates field
CELL = 2                              # GUI units a cell is across; a whole number keeps every cell the same size
MARGIN = 4                            # GUI units from the top right corner of the screen
ARROW = 6                             # GUI units across the player's arrow
LETTER = 5                            # GUI units across a compass letter
TEXTURES = "textures/ui/minimap/"
NO_CELL = "zz"

FIELD_SIZE = len(MARKER)
FIELD_ARROW = FIELD_SIZE + 1
FIELD_LETTER = FIELD_ARROW + 1
FIELD_COORDS_ON = FIELD_LETTER + 1
FIELD_COORDS = FIELD_COORDS_ON + 1
HEADER = FIELD_COORDS + COORDS
ROW = COLUMNS * 2


def field(start: int, length: int, source: str = "#preserved_text") -> str:
    """The bytes from start to start + length of a string, as a JSON UI expression."""
    if start == 0:
        return f"('%.{length}s' * {source})"
    return f"(('%.{start + length}s' * {source}) - ('%.{start}s' * {source}))"


def from_data(expression: str, target: str) -> dict:
    return {
        "binding_type": "view",
        "source_control_name": "minimap_data",
        "resolve_sibling_scope": True,
        "source_property_name": expression,
        "target_property_name": target,
    }


def showing(size: int) -> str:
    return f"({field(FIELD_SIZE, 1)} = '{SIZES.index(size)}')"


def data_control() -> dict:
    # the title is only there for a moment; this keeps the last map title until the next one, and is
    # visible only for the frame a new one arrives, which is when visibility_changed copies it over
    return {"minimap_data": {
        "type": "panel",
        "size": [0, 0],
        "property_bag": {"#preserved_text": ""},
        "bindings": [
            {"binding_name": "#hud_title_text_string"},
            {"binding_name": "#hud_title_text_string", "binding_name_override": "#preserved_text",
             "binding_condition": "visibility_changed"},
            {"binding_type": "view",
             "source_property_name": f"(not (#hud_title_text_string = #preserved_text) and not "
                                     f"((#hud_title_text_string - '{MARKER}') = #hud_title_text_string))",
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
        "bindings": [from_data(f"('r' + {field(HEADER + row * ROW, ROW)})", "#row")],
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
    """The arrow in the middle, the letter in the top edge and the coordinates under the map, at this size."""
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
        {f"minimap_letter_{size}": {
            "type": "image",
            "size": [LETTER, LETTER],
            "anchor_from": "top_right",
            "anchor_to": "top_right",
            "offset": [-(middle - LETTER / 2), CELL / 2 - LETTER / 2],
            "layer": 2,
            "texture": f"{TEXTURES}letter0",
            "bindings": [
                from_data(f"('{TEXTURES}letter' + {field(FIELD_LETTER, 1)})", "#texture"),
                from_data(showing(size), "#visible"),
            ],
        }},
        {f"minimap_coords_{size}": {
            "type": "label",
            "size": [120, 10],
            "anchor_from": "top_right",
            "anchor_to": "top_right",
            "offset": [0, span + 2],
            "layer": 2,
            "shadow": True,
            "text_alignment": "right",
            "text": "#value",
            "bindings": [
                from_data(field(FIELD_COORDS, COORDS), "#value"),
                from_data(f"({showing(size)} and ({field(FIELD_COORDS_ON, 1)} = 'y'))", "#visible"),
            ],
        }},
    ]


def hud() -> dict:
    controls = [data_control()]
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
                "size": [COLUMNS * CELL, COLUMNS * CELL + 12],
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
        f"export const COORDS = {COORDS};",
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
