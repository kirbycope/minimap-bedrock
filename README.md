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
pack holds the colours it is drawn with, so with only one of them you get nothing, or a grid of
question marks.

## Using it

**Hold a compass and use it** to open the menu. Every setting is a button, because the useful ones get
pressed over and over:

| Button | What it does |
| --- | --- |
| Zoom in, Zoom out | 1, 2, 4 or 8 blocks to a cell |
| Bigger, Smaller | 8, 12, 16, 20, 24, 32 or 40 blocks across |
| Move up, down, left, right | where on the screen the map sits |
| Turn with me | off keeps north at the top and turns the arrow instead |
| Mobs and players | the coloured dots |
| Coordinates | a line of numbers above the map |
| Hide the map | turns it off; the compass still opens this menu |

Everything is per player and is remembered between sessions.

If you would rather type, `/scriptevent minimap:menu` opens the same menu, and `minimap:on`,
`minimap:off`, `minimap:toggle` and `minimap:set <setting> <value>` do what they say. The settings are
`size`, `zoom`, `rotate`, `entities`, `coords`, `right` and `up`.

### What the map shows

North is up unless you turn that off. The letter in the top edge is which way up is, the white arrow in
the middle is you, and it points where you are looking.

The colours are Minecraft's own map colours, the ones the map in your hand is drawn with, and a cell is
drawn darker when it is lower than the cell to the north of it, which is what makes hills read as
hills. Water and lava colour the ground they lie on, so a coast reads as a coast: the game's own
"topmost block" answers with the floor of an ocean rather than the ocean, and the map asks what is
standing on that floor. A red dot is a monster, white is an animal or a villager, light blue is
another player and yellow is a dropped item.

Underground, the map shows the level you are standing on rather than the sky above it, and the same in
the Nether. Standing under a tree counts as being under a roof, so a forest shows its floor rather
than its canopy.

## Moving the map

The map starts in the top right corner on a 1920x1200 screen. On a smaller one it starts lower down and
further in, and the move buttons put it where you want it.

That is not fussiness: an add-on cannot ask Minecraft how big the screen is, or where to draw. The map
is text in the action bar, and the only say an add-on has over where that text goes is how much of it
there is. Spaces in front of each line push the map right, empty lines after it push the map up, and
the move buttons change those two numbers. It is why the position is a setting rather than a corner
you pick.

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

The map is action bar text, so another add-on's action bar message appears where the map is and the two
take turns. The resource pack also replaces `textures/ui/hud_tip_text_background` with nothing, which
takes the grey panel off the action bar, map or no map.

## How it is drawn, and what that costs it

Bedrock gives an add-on no way to draw pixels on the screen, so the map is text, written into the action
bar five times a second from a font the resource pack brings with it.

Two measurements decide everything else, and neither is a pack's to change:

- a line of text is ten pixels tall, whatever is written on it
- a glyph takes the width of the pixels it actually has, plus one

The ten is the floor on how fine the map can be, so one character carries **two** map pixels, stacked,
five pixels each, and four pixels of art plus Minecraft's one makes the columns five across as well. A
block is five screen pixels square. It is the idea behind drawing with braille dots in a terminal,
except that the pack supplies its own font, so each half is a full colour rather than a dot that is on
or off.

The price is combinations: a glyph has to exist for every pair of values that can sit one above the
other. Thirty-two colours in two brightness steps is 4096 glyphs, sixteen pages of the private use area,
which `tools/palette.py` draws. That is why the palette is thirty-two colours and the shading is two
steps rather than Minecraft's four.

What is left is the one pixel between characters, which no pack can remove. The glyphs leave a matching
pixel under each half so the grid over the map is even on all four sides rather than stripes down the
sides only.

A minimap mod on Java draws to the screen directly and has none of this: Xaero's can colour a block from
its own texture, at one screen pixel a block or finer. Five pixels a block is where an add-on stops.

## Development

The packs are the two `development_*_packs/minimap` folders, and three files in them are generated:

```bash
python tools/palette.py      # font/glyph_E1.png, font/glyph_E2.png, scripts/palette.js
python tools/pack_icon.py    # both pack_icon.png files
python -m pytest tests       # checks the manifests, the generated files and the imports
python tools/build_addon.py  # minimap-bedrock.mcaddon
python tools/make_thumbnail.py  # assets/thumbnail.png and the repository preview
```

`tools/palette.py` is the only place a colour is written down. It holds the colour of every block the
map knows, the rules it guesses the rest by, and the pixel sizes above, and it writes both the seventeen
glyph pages and the colour table the scripts read.

To see the map while working on it, point a Bedrock Dedicated Server at a world with both packs
junctioned into it, or copy them into the client's own `development_*_packs` folders. Changing a script
needs the world reloaded; changing anything in the resource pack needs the client restarted and the
pack's version bumped, because the client caches a pack by its id and version.

`/scriptevent minimap:calibrate` puts a ruler of glyphs on screen, which is how the numbers above were
measured and how to measure them again if Minecraft's font ever changes.

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

MIT. Nothing shipped inside the `.mcaddon` comes from anywhere else: the glyphs, the arrows and the icon
are all drawn by `tools/`. The thumbnail is set in Passion One, under the SIL Open Font License, which is
in the repository but not in either pack. See [CREDITS.md](CREDITS.md).
