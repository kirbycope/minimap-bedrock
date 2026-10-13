"""Checks the add-on holds together without Minecraft running.

What these can catch is everything that is written down twice: the pack ids the two manifests agree on,
the generated glyph pages and colour table against the tool that writes them, and the names the scripts
import against the names the modules export. Whether the map looks right is a question for the game.

    python -m pytest tests
"""

import json
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BEHAVIOR = os.path.join(ROOT, "development_behavior_packs", "minimap")
RESOURCE = os.path.join(ROOT, "development_resource_packs", "minimap")
SCRIPTS = os.path.join(BEHAVIOR, "scripts")


def read(path):
    with open(path, encoding="utf-8-sig") as handle:
        return json.load(handle)


def test_manifests_are_valid_json_with_the_parts_minecraft_requires():
    for pack in (BEHAVIOR, RESOURCE):
        manifest = read(os.path.join(pack, "manifest.json"))
        assert manifest["format_version"] == 2
        for field in ("name", "description", "uuid", "version", "min_engine_version"):
            assert field in manifest["header"], f"{pack} header has no {field}"
        assert manifest["modules"], f"{pack} declares no modules"


def test_the_behaviour_pack_depends_on_the_resource_pack_that_holds_the_glyphs():
    behaviour = read(os.path.join(BEHAVIOR, "manifest.json"))
    resource = read(os.path.join(RESOURCE, "manifest.json"))
    depends = [d for d in behaviour["dependencies"] if d.get("uuid") == resource["header"]["uuid"]]
    assert depends, "the behaviour pack does not depend on the resource pack"
    assert depends[0]["version"] == resource["header"]["version"], (
        "the dependency names a different version of the resource pack than the resource pack declares"
    )


def test_every_uuid_is_used_once():
    seen = {}
    for pack in (BEHAVIOR, RESOURCE):
        manifest = read(os.path.join(pack, "manifest.json"))
        for uuid in [manifest["header"]["uuid"]] + [module["uuid"] for module in manifest["modules"]]:
            assert uuid not in seen, f"{uuid} is used by both {seen.get(uuid)} and {pack}"
            seen[uuid] = pack


def test_the_script_entry_point_exists():
    behaviour = read(os.path.join(BEHAVIOR, "manifest.json"))
    entry = next(m["entry"] for m in behaviour["modules"] if m["type"] == "script")
    assert os.path.isfile(os.path.join(BEHAVIOR, entry)), f"{entry} is missing"


def test_the_generated_glyphs_and_colour_table_match_the_tool_that_writes_them():
    result = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "palette.py"), "--check"],
                            capture_output=True, text=True)
    assert result.returncode == 0, f"run tools/palette.py:\n{result.stdout}{result.stderr}"


def test_the_pack_icons_match_the_tool_that_writes_them():
    result = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "pack_icon.py"), "--check"],
                            capture_output=True, text=True, cwd=os.path.join(ROOT, "tools"))
    assert result.returncode == 0, f"run tools/pack_icon.py:\n{result.stdout}{result.stderr}"


def script(name):
    with open(os.path.join(SCRIPTS, name), encoding="utf-8") as handle:
        return handle.read()


def exported(name):
    return set(re.findall(r"^export (?:const|function|let) (\w+)", script(name), re.M))


@pytest.mark.parametrize("name", sorted(f for f in os.listdir(SCRIPTS) if f.endswith(".js")))
def test_every_name_a_script_imports_from_another_is_exported_by_it(name):
    for names, module in re.findall(r"import \{([^}]*)\} from \"\./([^\"]+)\"", script(name)):
        available = exported(module)
        for wanted in (part.strip() for part in names.split(",") if part.strip()):
            assert wanted in available, f"{name} imports {wanted} from {module}, which does not export it"


@pytest.mark.parametrize("name", sorted(f for f in os.listdir(SCRIPTS) if f.endswith(".js")))
def test_a_script_only_imports_modules_that_exist(name):
    for module in re.findall(r"from \"\./([^\"]+)\"", script(name)):
        assert os.path.isfile(os.path.join(SCRIPTS, module)), f"{name} imports {module}, which is missing"


def test_every_glyph_page_is_a_grid_of_sixteen_by_sixteen_whole_cells():
    from PIL import Image
    for page in sorted(f for f in os.listdir(os.path.join(RESOURCE, "font")) if f.startswith("glyph_")):
        image = Image.open(os.path.join(RESOURCE, "font", page))
        assert image.width % 16 == 0 and image.height % 16 == 0, f"{page} is not a grid of whole pixels"


def test_a_glyph_is_as_tall_as_its_cell_and_narrower_than_it():
    # A page's cells are square, so the cell has to be as tall as a line of text and the art is narrow
    # inside it. Minecraft takes a glyph's width from the pixels it can see, which is what makes the
    # map's columns five across rather than eleven.
    from PIL import Image
    table = script("palette.js")
    width = int(re.search(r"export const CELL_W = (\d+)", table).group(1))
    height = int(re.search(r"export const CELL_H = (\d+)", table).group(1))
    page = Image.open(os.path.join(RESOURCE, "font", "glyph_E1.png")).convert("RGBA")
    cell = page.width // 16
    assert page.width == page.height, "a glyph page must be square or Minecraft cuts the cells short"
    assert cell == height, "the cell is not as tall as a line of text, which would cut the glyph short"
    drawn = [x for x in range(cell) if page.getpixel((x, 1))[3]]
    assert drawn == list(range(width)), f"the art is {len(drawn)} pixels across, not {width}"
    down = "".join("#" if page.getpixel((1, y))[3] else "." for y in range(cell))
    assert down == "####.####.", f"the two halves and the lines between them are wrong: {down}"


def test_a_map_pixel_comes_out_square_at_the_sizes_the_glyphs_are_drawn():
    # A glyph takes the width of its art plus the one pixel Minecraft puts between characters, and a
    # line of text is ten pixels tall whatever is on it. The glyph holds two map pixels stacked, so a
    # map pixel is CELL_W + 1 across and CELL_H / 2 down, and those have to match.
    table = script("palette.js")
    width = int(re.search(r"export const CELL_W = (\d+)", table).group(1))
    height = int(re.search(r"export const CELL_H = (\d+)", table).group(1))
    assert width + 1 == height / 2, "map pixels would not be square: see tools/palette.py"


def test_there_is_a_glyph_page_for_every_pair_of_values():
    table = script("palette.js")
    values = int(re.search(r"export const VALUES = (\d+)", table).group(1))
    pages = [name for name in os.listdir(os.path.join(RESOURCE, "font")) if name.startswith("glyph_")]
    assert values ** 2 <= (len(pages) - 1) * 256, "a pair of values has no glyph: run tools/palette.py"


def test_every_size_puts_the_player_on_one_line_of_text():
    # A character is two map rows, so the four cells the player stands on have to fall on one of them.
    for size in re.search(r"export const SIZES = \[([^\]]*)\]", script("settings.js")).group(1).split(","):
        assert int(size) % 4 == 0, f"a map {size.strip()} across would split the player's own cells"
