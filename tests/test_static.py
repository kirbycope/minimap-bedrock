"""Checks the add-on holds together without Minecraft running.

What these can catch is everything that is written down twice: the pack ids the two manifests agree on,
the generated textures, HUD and colour table against the tools that write them, the HUD's bindings
against the title the script writes, and the names the scripts
import against the names the modules export. Whether the map looks right is a question for the game.

    python -m pytest tests
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

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


def test_the_behaviour_pack_depends_on_the_resource_pack_that_draws_the_map():
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


def test_the_generated_textures_and_colour_table_match_the_tool_that_writes_them():
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


def test_the_hud_and_the_title_layout_match_the_tool_that_writes_them():
    result = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "hud.py"), "--check"],
                            capture_output=True, text=True)
    assert result.returncode == 0, f"run tools/hud.py:\n{result.stdout}{result.stderr}"


# --- the HUD, read the way Minecraft reads it ------------------------------
#
# The map title is cut up by JSON UI expressions, and a byte out of place there draws a map shifted by a
# cell or not at all, with nothing in the content log to say why. So these evaluate the generated
# bindings the way the game does: '%.Ns' * text keeps the first N bytes, a - b takes every b out of a.


def evaluate(expression, properties):
    tokens = re.findall(r"'[^']*'|#\w+|\(|\)|\*|-|\+|=|\bnot\b|\band\b|\bor\b", expression)
    position = 0

    def peek():
        return tokens[position] if position < len(tokens) else None

    def take():
        nonlocal position
        position += 1
        return tokens[position - 1]

    def primary():
        token = take()
        if token == "(":
            value = binary(0)
            assert take() == ")"
            return value
        if token == "not":
            return not primary()
        if token.startswith("'"):
            return token[1:-1]
        return properties[token]

    levels = {"or": 1, "and": 2, "=": 3, "+": 4, "-": 4, "*": 5}

    def binary(floor):
        left = primary()
        while peek() in levels and levels[peek()] > floor:
            operator = take()
            right = binary(levels[operator])
            if operator == "*":
                width = int(re.fullmatch(r"%\.(\d+)s", left).group(1))
                left = right.encode()[:width].decode()
            elif operator == "-":
                left = left.replace(right, "") if right else left
            elif operator == "+":
                left = left + right
            elif operator == "=":
                left = left == right
            elif operator == "and":
                left = left and right
            else:
                left = left or right
        return left

    value = binary(0)
    assert position == len(tokens), f"left over in {expression}"
    return value


def hud_controls():
    hud = read(os.path.join(RESOURCE, "ui", "hud_screen.json"))
    return {name: body for control in hud["minimap"]["controls"][0]["minimap_map"]["controls"]
            for name, body in control.items()}


def drawn(title):
    """What the HUD shows for a title: each control's bound properties, the way the bindings set them."""
    controls = hud_controls()
    state = {"minimap_data": {"#preserved_text": title}}
    for name, body in controls.items():
        if name == "minimap_data":
            continue
        properties = {}
        for binding in body.get("bindings", []):
            source = state[binding["source_control_name"]]
            properties[binding["target_property_name"]] = evaluate(binding["source_property_name"], source)
        state[name] = properties
    return state


def layout():
    table = script("hud_layout.js")
    number = lambda name: int(re.search(rf"export const {name} = (\d+)", table).group(1))
    text = lambda name: re.search(rf'export const {name} = "([^"]*)"', table).group(1)
    sizes = [int(s) for s in re.search(r"export const SIZES = \[([^\]]*)\]", table).group(1).split(",")]
    return text("MARKER"), sizes, number("COLUMNS"), number("COORDS"), text("NO_CELL")


def test_every_cell_of_the_hud_shows_the_value_the_title_gives_it():
    marker, sizes, columns, coords, none = layout()
    size = sizes[2]
    span = size + 2
    grid = [[(row * 7 + column * 3) % 64 for column in range(span)] for row in range(span)]
    # and a row of one value, because '-' takes away every copy and a repeat is where slicing goes wrong
    grid[1] = [5] * span
    title = marker + str(sizes.index(size)) + "5" + "2" + "y" + "12, 64, -3".rjust(coords)
    for row in grid:
        title += "".join(f"{row[span - 1 - cell]:02x}" if cell < span else none for cell in range(columns))
    state = drawn(title)
    for row in range(columns):
        for cell in range(columns):
            texture = state[f"minimap_c{row}_{cell}"]["#texture"]
            if row < span and cell < span:
                assert texture == f"textures/ui/minimap/c{grid[row][span - 1 - cell]:02x}", (row, cell, texture)
            else:
                assert texture in ("textures/ui/minimap/c", f"textures/ui/minimap/c{none}"), (row, cell, texture)
    for each in sizes:
        shown = each == size
        assert state[f"minimap_arrow_{each}"]["#visible"] == shown
        assert state[f"minimap_letter_{each}"]["#visible"] == shown
        assert state[f"minimap_coords_{each}"]["#visible"] == shown
    assert state[f"minimap_arrow_{size}"]["#texture"] == "textures/ui/minimap/arrow5"
    assert state[f"minimap_letter_{size}"]["#texture"] == "textures/ui/minimap/letter2"
    assert state[f"minimap_coords_{size}"]["#value"].strip() == "12, 64, -3"


def test_every_texture_the_hud_can_name_is_in_the_pack():
    marker, sizes, columns, coords, none = layout()
    folder = os.path.join(RESOURCE, "textures", "ui", "minimap")
    values = int(re.search(r"export const VALUES = (\d+)", script("palette.js")).group(1))
    arrows = int(re.search(r"export const ARROWS = (\d+)", script("palette.js")).group(1))
    names = ["c", f"c{none}"] + [f"c{value:02x}" for value in range(values)]
    names += [f"arrow{n}" for n in range(arrows)] + [f"letter{n}" for n in range(4)]
    for name in names:
        assert os.path.isfile(os.path.join(folder, f"{name}.png")), f"textures/ui/minimap/{name}.png is missing"


def test_the_script_writes_a_title_the_hud_reads():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    marker, sizes, columns, coords, none = layout()
    with tempfile.TemporaryDirectory() as folder:
        for name in ("render.js", "palette.js", "hud_layout.js"):
            shutil.copy(os.path.join(SCRIPTS, name), folder)
        # terrain.js reads the world; this one answers with a colour by the column's x, so east and
        # west can be told apart on the map
        with open(os.path.join(folder, "terrain.js"), "w") as handle:
            handle.write("export function layerFor() { return 0; }\n"
                         "export function columnAt(d, l, x, z) { return { c: x > 0 ? 2 : 12, y: 64 }; }\n")
        with open(os.path.join(folder, "run.mjs"), "w") as handle:
            handle.write("import { draw } from './render.js';\n"
                         "const player = { id: 1, location: { x: 0.5, y: 64, z: 0.5 }, dimension: {},"
                         " getRotation: () => ({ x: 0, y: 90 }) };\n"
                         "process.stdout.write(draw(player, { size: 16, zoom: 1, rotate: false,"
                         " entities: false, coords: true }, 0));\n")
        title = subprocess.run([node, os.path.join(folder, "run.mjs")], capture_output=True, text=True,
                               check=True).stdout
    state = drawn(title)
    size = 16
    span = size + 2
    texture = lambda row, cell: state[f"minimap_c{row}_{cell}"]["#texture"][len("textures/ui/minimap/c"):]
    shade = lambda colour: [f"{colour * 2 + step:02x}" for step in (0, 1)]
    # the right-hand half of the map is east of the player, x > 0
    assert texture(span // 2, 1) in shade(2), "the map's east edge is not on the right"
    assert texture(span // 2, span - 2) in shade(12), "the map's west edge is not on the left"
    assert texture(0, 0) in shade(1) and texture(span - 1, span - 1) in shade(1), "the frame is missing"
    assert texture(0, span) in ("", none) and texture(span, 0) in ("", none), "the map runs past its frame"
    assert state[f"minimap_arrow_{size}"]["#visible"]
    # facing west with north up, so the arrow is the seventh of eight, counting clockwise from north
    assert state[f"minimap_arrow_{size}"]["#texture"] == "textures/ui/minimap/arrow6"
    assert state[f"minimap_coords_{size}"]["#value"].strip() == "0, 64, 0"


# --- the project art -------------------------------------------------------
#
# The thumbnail is not part of either pack, so these only check that it can be
# rebuilt from what is committed and that it came out at the sizes the README
# and the portfolio site expect.

ASSETS = os.path.join(ROOT, "assets")


def test_everything_the_thumbnail_is_built_from_is_committed():
    for name in ("background.png", "skin.png"):
        assert os.path.isfile(os.path.join(ASSETS, name)), \
            f"assets/{name} is missing, so the thumbnail cannot be rebuilt"
    assert os.path.isfile(os.path.join(ROOT, "tools", "fonts", "PassionOne-Black.ttf")), \
        "the title font is missing"


def test_the_skin_is_a_64x64_classic_model():
    from PIL import Image
    with Image.open(os.path.join(ASSETS, "skin.png")) as skin:
        assert skin.size == (64, 64)
        # tools/skin_render.py unwraps the 4px-arm layout, not the slim one
        arm = skin.convert("RGBA").crop((47, 20, 48, 32))
        assert max(p[3] for p in arm.getdata()) > 0, "skin_render.py expects the classic 4px arm"


def test_the_master_is_1920x1080():
    from PIL import Image
    with Image.open(os.path.join(ASSETS, "thumbnail.png")) as image:
        assert image.size == (1920, 1080)


def test_the_preview_is_the_size_the_readme_embeds():
    from PIL import Image
    with Image.open(os.path.join(ROOT, "minimap-bedrock.png")) as image:
        assert image.size == (960, 540)


def test_the_minimap_box_is_inside_the_capture():
    from PIL import Image
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import make_thumbnail
    with Image.open(os.path.join(ASSETS, "background.png")) as plate:
        left, top, right, bottom = make_thumbnail.MINIMAP_BOX
        assert 0 <= left < right <= plate.width, "MINIMAP_BOX runs off the capture"
        assert 0 <= top < bottom <= plate.height, "MINIMAP_BOX runs off the capture"
        assert make_thumbnail.PLATE_CROP[2] <= plate.width
        assert make_thumbnail.PLATE_CROP[3] <= plate.height
