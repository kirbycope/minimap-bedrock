![Minimap](/minimap-bedrock.png)

# minimap-bedrock

A minimap for Minecraft Bedrock Edition. It draws the ground around you, in colour, in the corner of
the screen, and it is all add-on: no mods, no client changes, Windows, console and phone alike.

## Installation

1. Download the [mcaddon](https://github.com/kirbycope/minimap-bedrock/releases/latest/download/minimap-bedrock.mcaddon) from the latest release
1. Double-click the `.mcaddon` file
1. Edit world
   - Activate the Behavior pack
   - Activate the Resource pack

Both packs are needed. The behaviour pack works out what the map should look like and the resource
pack draws it, so with only one of them you get nothing, or a title full of hex in the middle of the
screen.

## Using it

**Hold a compass and use it** to open the menu. Every setting is a button, because the useful ones get
pressed over and over:

| Button | What it does |
| --- | --- |
| Zoom in, Zoom out | 1, 2, 4 or 8 blocks to a cell |
| Bigger, Smaller | 8, 12, 16, 20, 24, 32 or 40 blocks across |
| Turn with me | off keeps north at the top and turns the arrow instead |
| Mobs and players | the coloured dots |
| Shape | square, or round as Xaero's minimap draws it |
| Chunk grid | a dashed line along every chunk edge |
| Slime chunks | a green checker over the chunks slimes spawn in |
| Waypoints | add a named, coloured waypoint where you stand, delete one, and show or hide them and where you last died |
| Coordinates, Facing, Biome, Light level, Time of day | the lines of text under the map, each on or off |
| Hide the map | turns it off; the compass still opens this menu |

Everything is per player and is remembered between sessions.

If you would rather type, `/scriptevent minimap:menu` opens the same menu, and `minimap:on`,
`minimap:off`, `minimap:toggle` and `minimap:set <setting> <value>` do what they say. The settings are
`size`, `zoom`, `shape` (`square` or `circle`), `rotate`, `entities`, and the lines under the map:
`coords`, `angle`, `biome`, `light` and `time`, each `true` or `false`, `waypoints` and `deathpoint`
for the marks, and `grid` and `slime` for the overlays. `minimap:waypoint [colour] [name]` adds a waypoint where you stand; the colours are red,
orange, yellow, green, aqua, blue, purple, pink and white.

### What the map shows

North is up unless you turn that off. N, E, S and W sit in the edges of the frame, and the red arrow in
the middle is you, pointing where you are looking.

The colours are Minecraft's own map colours, the ones the map in your hand is drawn with, and a cell is
drawn darker when it is lower than the cell to the north of it, which is what makes hills read as
hills. Water and lava colour the ground they lie on, so a coast reads as a coast: the game's own
"topmost block" answers with the floor of an ocean rather than the ocean, and the map asks what is
standing on that floor. A red dot is a monster, white is an animal or a villager, light blue is
another player and yellow is a dropped item.
A waypoint is a plus in its colour and the place you last died is a black X. One too far away to be on
the map is held at the map's edge in the direction it lies, as Xaero's minimap does, so you can steer
for it.

The overlays go over every other cell, so the ground still shows through. Slime chunks are worked out
the way Bedrock picks them, from the chunk's own position rather than the world seed (`scripts/slime.js`,
checked against SlimeChunkFinderAddonBE's generator in the tests), so they are right in every world. Under the map go whichever lines are on, in this order: your block coordinates, the way you face with
the camera's yaw and pitch, the biome, the block and sky light where you stand, and the day and the hour.

Underground, the map shows the level you are standing on rather than the sky above it, and the same in
the Nether. Standing under a tree counts as being under a roof, so a forest shows its floor rather
than its canopy.

## Where the map sits

In the top right corner, on every screen. The resource pack adds the map to the HUD anchored to that
corner, so it is in the same place at any window size and interface scale, and it hides with the rest of
the HUD.

## What it costs, and how far it can see

A pass over every player's map takes about 1 ms at the size it starts at, and up to about 15 ms on the
largest map there is; a pass runs every four ticks. The map does not re-read the world each time: a
column of blocks is remembered until someone builds there or twenty seconds pass, and each pass reads
only enough columns to fill the biggest map on screen in about ten of them, so a map fills in over
roughly half a second when you arrive somewhere new. `/scriptevent minimap:perf` prints the last and
worst pass.

The map can only show ground the game is holding in memory, which is the chunks near you, and while you
are moving the ground ahead has not arrived yet. So Bigger and Zoom out stop once the map would look
more than 48 blocks out, and say so on the button. Past that the extra map is black however long you
wait, which is what a 40 cell map at 8 blocks a cell used to be.

## What else it touches

The map travels from the behaviour pack to the HUD as a title starting `mm:map`, and the resource pack
hides the vanilla title while one is up. So a title from a command or another add-on is cut short when
the map changes, which is at most five times a second while you move and once every five seconds while
you stand still; turning the map off stops the titles altogether. The action bar is left alone.

It sits alongside [cobblemon-bedrock](https://github.com/kirbycope/cobblemon-bedrock), which carries its
HUD in titles the same way: each pack hides the other's titles as well as its own, so they can be in
either order.

## How it is drawn

An add-on cannot draw on the screen, but a resource pack can add controls to the HUD, and a HUD control
can read the title text. So `ui/hud_screen.json` is a grid of image controls, one per map cell, 42 by 42
for the largest map and its frame. The script writes the map as a title, two hex digits a cell, and each
control cuts its two characters out of the title and shows the texture they name:
`textures/ui/minimap/caa.png` to `cdp.png`, one per colour and brightness step, the value's two hex
digits written a to p. Letters rather than digits, because JSON UI reads a slice that starts with a
number as that number, so `03` would come out as 3 and name no texture.

JSON UI can only cut a string at a byte count it is given (`'%.Ns'` keeps the first N bytes, and taking
a shorter prefix away from a longer one leaves the bytes between), so the titles are fixed width. The game refuses a title over 512 characters, so a map is ten of them,
sent one a tick and only when they changed: a header with the size, the arrow, the four compass letters
and the lines of text, then nine chunks of five rows each, 42 cells wide whatever the map's size, the
right-hand cell first so the map grows out of its corner. A row control cuts its row out of its chunk
once, and its cells cut from that, so no cell works on a whole title.
The HUD keeps the last map title until the next one (the "preserved title" pattern cobblemon-bedrock's
party uses), which is why the script only sends one when the map changed.

What that buys over drawing the map as text, which is how it was drawn before: a cell is a square of
real pixels, two interface units across, with no gap between cells; the map sits in a corner rather than
where the action bar puts it; and the palette is no longer held to 64 values by needing a glyph for every
pair of them, since two hex digits can name 256.

The arrow, the compass letters and the lines of text are controls of their own over the cells. A
control's position cannot be bound, so there is a set for every map size and the header says which to
show. Each line carries its own flag in the header, the size again when it is on, because JSON UI did
not honour `and` between two slices; one comparison per control is what works.

## Development

The packs are the two `development_*_packs/minimap` folders, and most of the resource pack is generated:

```bash
python tools/palette.py      # textures/ui/minimap/*.png, scripts/palette.js
python tools/hud.py          # ui/hud_screen.json, scripts/hud_layout.js
python tools/pack_icon.py    # both pack_icon.png files
python -m pytest tests       # checks the manifests, the generated files and the imports
python tools/build_addon.py  # minimap-bedrock.mcaddon
python tools/make_thumbnail.py  # assets/thumbnail.png and the repository preview
```

`tools/palette.py` is the only place a colour is written down. It holds the colour of every block the
map knows and the rules it guesses the rest by, and it writes the cell textures and the colour table the
scripts read. `tools/hud.py` is the only place the title's layout is written down, and it writes both
the HUD that reads the title and the constants the script writes it with. The tests evaluate the HUD's
bindings the way the game does, against a title from the real `render.js`, so a byte out of place in
either fails there rather than in the game.

To see the map while working on it, point a Bedrock Dedicated Server at a world with both packs
junctioned into it, or copy them into the client's own `development_*_packs` folders. Changing a script
needs the world reloaded; changing anything in the resource pack needs the client restarted and the
pack's version bumped, because the client caches a pack by its id and version.

### The thumbnail

`python tools/make_thumbnail.py` rebuilds the picture at the top of this file. It needs nothing but what
is committed: a capture of the map on screen in `assets/background.png`, the player skin in
`assets/skin.png` and Passion One in `tools/fonts/`. It writes the 1920x1080 master to
`assets/thumbnail.png` and hands that to `tools/make_preview.py`, which writes the 960x540
`minimap-bedrock.png` the README and the portfolio site use.

The minimap is lifted out of the capture by `MINIMAP_BOX` and blown up with nearest-neighbour, because
at its real size it is unreadable in a thumbnail. `_patch_out()` mirrors the strip beside it over the
original first, so no sliver of the small one shows past the blown-up copy's edge. Re-run the tool after
anything that changes how the map looks, and take a fresh capture first.

| | |
| --- | --- |
| `tools/make_thumbnail.py` | Builds `assets/thumbnail.png` and the 960x540 repository preview |
| `tools/skin_render.py` | Renders the posed player from `assets/skin.png` |
| `tools/make_preview.py` | Resizes a 16:9 screenshot to the 960x540 preview |
| `tools/tinyify.py` | Compresses PNGs losslessly, in place |
| `tools/bridge.py`, `tools/client_drive.py` | Run commands on the server and drive the real client |

## Licence

MIT. Nothing shipped inside the `.mcaddon` comes from anywhere else: the cells, the arrows, the letters
and the icon are all drawn by `tools/`. The thumbnail is set in Passion One, under the SIL Open Font License, which is
in the repository but not in either pack. See [CREDITS.md](CREDITS.md).
