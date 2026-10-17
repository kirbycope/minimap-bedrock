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
# bindings the way the game does: '%.Ns' * text keeps the first N bytes, a - b takes every b out of a,
# and a string made only of digits becomes a number, which is how "03" turns into 3 (an earlier version of
# this HUD named its textures in hex and drew one cell in a hundred because of it).


def numeric(value):
    """JSON UI's reading of a slice: one that starts with a number, after any spaces, is that number."""
    if not isinstance(value, str):
        return value
    number = re.match(r"\s*(-?\d+)", value)
    return int(number.group(1)) if number else value


def evaluate(expression, properties):
    tokens = re.findall(r"'[^']*'|#\w+|\b\d+\b|\(|\)|\*|-|\+|=|>|\bnot\b|\band\b|\bor\b", expression)
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
        if token.isdigit():
            return int(token)
        return properties[token]

    levels = {"or": 1, "and": 2, "=": 3, ">": 3, "+": 4, "-": 4, "*": 5}

    def binary(floor):
        left = primary()
        while peek() in levels and levels[peek()] > floor:
            operator = take()
            right = binary(levels[operator])
            if operator == "*":
                width = int(re.fullmatch(r"%\.(\d+)s", left).group(1))
                left = numeric(str(right).encode()[:width].decode())
            elif operator == "-":
                left = numeric(str(left).replace(str(right), "") if str(right) else left)
            elif operator == "+":
                left = str(left) + str(right)
            elif operator == "=":
                left = left == right
            elif operator == ">":
                # only between numbers; a slice that did not come out a number compares as false
                left = isinstance(left, int) and isinstance(right, int) and left > right
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


def drawn(titles):
    """What the HUD shows for a map's titles (the header, then the row chunks): each control's bound
    properties, the way the bindings set them. Each data control keeps the title with its marker."""
    controls = hud_controls()
    head_marker, chunk = layout_extra()
    state = {"minimap_data": {"#preserved_text": titles[0]}}
    for number, title in enumerate(titles[1:]):
        assert title.startswith(f"{layout()[0]}r{number:02d}"), title[:12]
        state[f"minimap_k{number}"] = {"#preserved_text": title}
    for name, body in controls.items():
        if name in state:
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
    return text("MARKER"), sizes, number("COLUMNS"), (number("INFO"), number("INFO_WIDTH")), text("NO_CELL")


def layout_extra():
    table = script("hud_layout.js")
    return (re.search(r'export const HEAD_MARKER = "([^"]*)"', table).group(1),
            int(re.search(r"export const CHUNK = (\d+)", table).group(1)))


def code(value):
    """A value's two letters, as tools/palette.py names its texture: its hex digits written a to p."""
    return "".join(chr(ord("a") + int(digit, 16)) for digit in f"{value:02x}")


def test_every_cell_of_the_hud_shows_the_value_the_title_gives_it():
    marker, sizes, columns, info, none = layout()
    size = sizes[2]
    span = size + 2
    grid = [[(row * 7 + column * 3) % 64 for column in range(span)] for row in range(span)]
    # and a row of one value, because '-' takes away every copy and a repeat is where slicing goes wrong
    grid[1] = [5] * span
    head_marker, chunk = layout_extra()
    rows = ["".join(code(row[span - 1 - cell]) if cell < span else none for cell in range(columns)) for row in grid]
    lines, width = info
    # two lines on, the rest blank, which the HUD must not show
    text = ["XYZ: 12, 64, -3", "Plains", "", "", ""]
    titles = [head_marker + str(sizes.index(size)) + "5" + "2301" + str(sizes.index(size)) * 2 + "---" + "".join(line.rjust(width) for line in text)]
    titles += [f"{marker}r{n:02d}" + "".join(rows[n * chunk:n * chunk + chunk]) for n in range(-(-columns // chunk))]
    state = drawn(titles)
    for row in range(columns):
        for cell in range(columns):
            texture = state[f"minimap_c{row}_{cell}"]["#texture"]
            if row < span and cell < span:
                assert texture == f"textures/ui/minimap/c{code(grid[row][span - 1 - cell])}", (row, cell, texture)
            else:
                assert texture in ("textures/ui/minimap/c", f"textures/ui/minimap/c{none}"), (row, cell, texture)
    for each in sizes:
        shown = each == size
        assert state[f"minimap_arrow_{each}"]["#visible"] == shown
        for edge in range(4):
            assert state[f"minimap_letter_{each}_{edge}"]["#visible"] == shown
        for line in range(lines):
            assert state[f"minimap_info_{each}_{line}"]["#visible"] == (shown and text[line] != ""), (each, line)
    assert state[f"minimap_arrow_{size}"]["#texture"] == "textures/ui/minimap/arrow5"
    assert [state[f"minimap_letter_{size}_{edge}"]["#texture"] for edge in range(4)] == \
        [f"textures/ui/minimap/letter{n}" for n in (2, 3, 0, 1)]
    assert [state[f"minimap_info_{size}_{line}"]["#text"].strip() for line in (0, 1)] == ["XYZ: 12, 64, -3", "Plains"]


def test_every_texture_the_hud_can_name_is_in_the_pack():
    marker, sizes, columns, info, none = layout()
    folder = os.path.join(RESOURCE, "textures", "ui", "minimap")
    values = int(re.search(r"export const VALUES = (\d+)", script("palette.js")).group(1))
    arrows = int(re.search(r"export const ARROWS = (\d+)", script("palette.js")).group(1))
    names = ["c", f"c{none}"] + [f"c{code(value)}" for value in range(values)]
    names += [f"arrow{n}" for n in range(arrows)] + [f"letter{n}" for n in range(4)]
    for name in names:
        assert os.path.isfile(os.path.join(folder, f"{name}.png")), f"textures/ui/minimap/{name}.png is missing"


def rendered(settings, properties=None):
    """The titles render.js draws for a player at 0.5, 64, 0.5 facing west, with these settings over
    a 16 cell map at a block a cell, and these dynamic properties on the player."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    with tempfile.TemporaryDirectory() as folder:
        for name in ("render.js", "palette.js", "hud_layout.js", "waypoints.js", "slime.js"):
            shutil.copy(os.path.join(SCRIPTS, name), folder)
        # terrain.js reads the world; this one answers with a colour by the column's x, so east and
        # west can be told apart on the map
        with open(os.path.join(folder, "terrain.js"), "w") as handle:
            handle.write("export function layerFor() { return 0; }\n"
                         "export function columnAt(d, l, x, z) { return { c: x > 0 ? 2 : 12, y: 64 }; }\n")
        # and @minecraft/server only has to tell the time and take a death listener
        server = os.path.join(folder, "node_modules", "@minecraft", "server")
        os.makedirs(server)
        with open(os.path.join(server, "package.json"), "w") as handle:
            handle.write('{"name": "@minecraft/server", "type": "module", "main": "index.js"}\n')
        with open(os.path.join(server, "index.js"), "w") as handle:
            handle.write("export const world = { getTimeOfDay: () => 7500, getDay: () => 3,"
                         " afterEvents: { entityDie: { subscribe() {} } } };\n")
        everything = {"size": 16, "zoom": 1, "rotate": False, "entities": False, "waypoints": False,
                      "deathpoint": False, "grid": False, "slime": False, "shape": "square", **settings}
        with open(os.path.join(folder, "run.mjs"), "w") as handle:
            handle.write("import { draw } from './render.js';\n"
                         f"const properties = {json.dumps(properties or {})};\n"
                         "const dimension = { id: 'minecraft:overworld',"
                         " getBiome: () => ({ id: 'minecraft:dark_forest' }),"
                         " getLightLevel: () => 7, getSkyLightLevel: () => 15 };\n"
                         "const player = { id: 1, location: { x: 0.5, y: 64, z: 0.5 }, dimension,"
                         " getRotation: () => ({ x: 0, y: 90 }), getDynamicProperty: (key) => properties[key] };\n"
                         f"process.stdout.write(JSON.stringify(draw(player, {json.dumps(everything)}, 0)));\n")
        with open(os.path.join(folder, "package.json"), "w") as handle:
            handle.write('{"type": "module"}\n')   # so an older node reads the scripts as modules too
        return json.loads(subprocess.run([node, os.path.join(folder, "run.mjs")], capture_output=True,
                                          text=True, check=True).stdout)


def test_the_script_writes_a_title_the_hud_reads():
    marker, sizes, columns, info, none = layout()
    titles = rendered({"coords": True, "angle": True, "biome": True, "light": True, "time": True})
    assert all(len(title) <= 512 for title in titles), "the server refuses a title over 512 characters"
    state = drawn(titles)
    size = 16
    span = size + 2
    texture = lambda row, cell: state[f"minimap_c{row}_{cell}"]["#texture"][len("textures/ui/minimap/c"):]
    shade = lambda colour: [code(colour * 2 + step) for step in (0, 1)]
    # the right-hand half of the map is east of the player, x > 0
    assert texture(span // 2, 1) in shade(2), "the map's east edge is not on the right"
    assert texture(span // 2, span - 2) in shade(12), "the map's west edge is not on the left"
    assert texture(0, 0) in shade(1) and texture(span - 1, span - 1) in shade(1), "the frame is missing"
    assert texture(0, span) in ("", none) and texture(span, 0) in ("", none), "the map runs past its frame"
    assert state[f"minimap_arrow_{size}"]["#visible"]
    # facing west with north up, so the arrow is the seventh of eight, counting clockwise from north
    assert state[f"minimap_arrow_{size}"]["#texture"] == "textures/ui/minimap/arrow6"
    assert [state[f"minimap_info_{size}_{line}"]["#text"].strip() for line in range(5)] == \
        ["XYZ: 0, 64, 0", "W 90.0 / 0.0", "Dark Forest", "Light: 7 (sky 15)", "Day 3, 13:30"]


def test_waypoints_draw_and_one_off_the_map_is_held_at_its_edge():
    palette = script("palette.js")
    red = json.loads(re.search(r"export const WAYPOINT_COLOURS = (\{[^}]*\})", palette).group(1))["red"]
    death = int(re.search(r"export const DEATH = (\d+)", palette).group(1))
    far_east = [{"name": "Base", "colour": "red", "x": 100, "y": 64, "z": 0, "dimension": "minecraft:overworld"}]
    nearby = {"x": -3, "y": 64, "z": 0, "dimension": "minecraft:overworld"}
    titles = rendered({"waypoints": True, "deathpoint": True},
                      {"minimap:waypoints": json.dumps(far_east), "minimap:death": json.dumps(nearby)})
    state = drawn(titles)
    texture = lambda row, cell: state[f"minimap_c{row}_{cell}"]["#texture"][len("textures/ui/minimap/c"):]
    bright = lambda colour: code(colour * 2 + 1)
    # a hundred blocks east of a 16 cell map: held a cell in from the frame's east edge, mid height,
    # which is the frame's row 9 and, counting from the right, its cell 2
    assert texture(9, 2) == bright(red), "the waypoint is not held at the east edge"
    assert texture(8, 2) == bright(red) and texture(9, 1) == bright(red), "the waypoint is not a plus"
    # three blocks west, drawn where it is, as an X
    assert texture(9, 11) == bright(death), "the deathpoint is not where the player died"
    assert texture(8, 10) == bright(death) and texture(10, 12) == bright(death), "the deathpoint is not an X"


# chunk x, z from -6 to 6, as SlimeChunkFinderAddonBE's MT19937 picks them
SLIME_CHUNKS = [(-6, 0), (-4, -1), (-4, 2), (-3, -2), (-3, -1), (-1, 0), (0, -5), (0, -2), (0, 4), (0, 6),
                (1, -2), (3, 0), (3, 1), (4, -6), (6, -4), (6, 5)]


def test_slime_chunks_are_the_ones_bedrock_spawns_slimes_in():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    with tempfile.TemporaryDirectory() as folder:
        shutil.copy(os.path.join(SCRIPTS, "slime.js"), folder)
        with open(os.path.join(folder, "package.json"), "w") as handle:
            handle.write('{"type": "module"}\n')
        with open(os.path.join(folder, "run.mjs"), "w") as handle:
            handle.write("import { isSlimeChunk } from './slime.js';\n"
                         "const found = [];\n"
                         "for (let x = -6; x <= 6; x++) for (let z = -6; z <= 6; z++)"
                         " if (isSlimeChunk(x, z)) found.push([x, z]);\n"
                         "process.stdout.write(JSON.stringify(found));\n")
        found = json.loads(subprocess.run([node, os.path.join(folder, "run.mjs")], capture_output=True,
                                          text=True, check=True).stdout)
    # what SlimeChunkFinderAddonBE's own Mersenne Twister gives for the same chunks
    assert [tuple(chunk) for chunk in found] == SLIME_CHUNKS


def test_the_chunk_grid_runs_along_chunk_edges():
    palette = script("palette.js")
    grid = int(re.search(r"export const GRID = (\d+)", palette).group(1))
    state = drawn(rendered({"grid": True}))
    texture = lambda row, cell: state[f"minimap_c{row}_{cell}"]["#texture"][len("textures/ui/minimap/c"):]
    # the player is at x 0.5, and block 0, which starts a chunk, is the map's column 7 (Math.round takes
    # its -0.5 to 0): the frame's column 8, which is cell 9 counting from the right of an 18 cell frame
    lined = [row for row in range(1, 17) if texture(row, 9) == code(grid * 2 + 1)]
    assert lined and all(row % 2 == lined[0] % 2 for row in lined) and len(lined) >= 7, lined


def test_the_enlarged_map_is_the_biggest_the_zoom_allows():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    with tempfile.TemporaryDirectory() as folder:
        for name in ("settings.js", "hud_layout.js"):
            shutil.copy(os.path.join(SCRIPTS, name), folder)
        with open(os.path.join(folder, "package.json"), "w") as handle:
            handle.write('{"type": "module"}\n')
        with open(os.path.join(folder, "run.mjs"), "w") as handle:
            handle.write("import { shownWith } from './settings.js';\n"
                         "process.stdout.write(JSON.stringify([1, 2, 4, 8].map((zoom) =>"
                         " shownWith({ size: 16, zoom, enlarged: true }).size).concat("
                         "shownWith({ size: 16, zoom: 2, enlarged: false }).size)));\n")
        sizes = json.loads(subprocess.run([node, os.path.join(folder, "run.mjs")], capture_output=True,
                                          text=True, check=True).stdout)
    # 40 cells at 1 and 2 blocks a cell stay inside the 48 blocks the game answers for, 24 at 4, 12 at 8
    assert sizes == [40, 40, 24, 12, 16]


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
