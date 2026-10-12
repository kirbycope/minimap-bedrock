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


def test_the_glyph_pages_are_square_grids_of_sixteen_cells():
    from PIL import Image
    for page in ("glyph_E1.png", "glyph_E2.png"):
        image = Image.open(os.path.join(RESOURCE, "font", page))
        assert image.width == image.height, f"{page} is not square"
        assert image.width % 16 == 0, f"{page} is not a 16 by 16 grid of whole pixels"


def test_the_cell_size_the_scripts_use_is_the_one_the_pages_were_drawn_at():
    from PIL import Image
    declared = int(re.search(r"export const CELL = (\d+)", script("palette.js")).group(1))
    page = Image.open(os.path.join(RESOURCE, "font", "glyph_E1.png"))
    assert page.width // 16 == declared, "palette.js and the glyph page disagree about the cell size"


def test_the_map_stays_square_at_the_cell_size_minecraft_draws_it():
    # a glyph is as wide as its cell plus one and a line of text is ten pixels tall, so only one cell
    # size comes out square. The map is drawn as action bar text and cannot change either number.
    declared = int(re.search(r"export const CELL = (\d+)", script("palette.js")).group(1))
    assert declared + 1 == 10, "cells would not be square: see tools/palette.py"
