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
| Bigger, Smaller | 7, 9, 11, 13 or 15 cells across |
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

The colours are Minecraft's own map colours, the ones the map in your hand is drawn with, and each cell
is shaded against the cell to the north of it, which is what makes hills read as hills. A red dot is a monster, white is an animal or a villager, light blue is
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

## What it costs

A pass over every player's map takes 1 to 2 ms on a dedicated server, and a pass runs every four ticks.
The map does not re-read the world each time: a column of blocks is remembered until someone builds
there or twenty seconds pass, and only sixty-four columns are read per pass, so a map fills in over
about half a second when you arrive somewhere new. `/scriptevent minimap:perf` prints the last and
worst pass.

## What else it touches

The map is action bar text, so another add-on's action bar message appears where the map is and the two
take turns. The resource pack also replaces `textures/ui/hud_tip_text_background` with nothing, which
takes the grey panel off the action bar, map or no map.

## How it is drawn, and what that costs it

Bedrock gives an add-on no way to draw pixels on the screen, so the map is text. The resource pack adds
a font page where every glyph is a solid square of colour, and the behaviour pack writes one character
per cell into the action bar, five times a second.

That is also the ceiling on how good it can look. Minecraft draws a glyph one screen pixel per texture
pixel, puts one pixel between characters and makes every line ten pixels tall whatever is on it. So a
cell cannot be smaller than about ten pixels, and there is a one pixel line between cells that nothing
in a pack can remove. Drawing the cells nine pixels across, as `tools/palette.py` does, is what puts
that line evenly on all four sides and makes the cell square; a cell of ten closes the line between
rows and leaves it down the sides only, which looks worse.

A minimap mod on Java draws to the screen directly and has none of this. This is as close as an add-on
gets: the same colours and the same shading, in cells the size of a letter.

## Development

The packs are the two `development_*_packs/minimap` folders, and three files in them are generated:

```bash
python tools/palette.py      # font/glyph_E1.png, font/glyph_E2.png, scripts/palette.js
python tools/pack_icon.py    # both pack_icon.png files
python -m pytest tests       # checks the manifests, the generated files and the imports
python tools/build_addon.py  # minimap-bedrock.mcaddon
```

`tools/palette.py` is the only place a colour is written down. It holds the colour of every block the
map knows, the rules it guesses the rest by, and the pixel size of a cell, and it writes both the glyph
pages and the colour table the scripts read.

To see the map while working on it, point a Bedrock Dedicated Server at a world with both packs
junctioned into it, or copy them into the client's own `development_*_packs` folders. Changing a script
needs the world reloaded; changing anything in the resource pack needs the client restarted and the
pack's version bumped, because the client caches a pack by its id and version.

`/scriptevent minimap:calibrate` puts a ruler of glyphs on screen, which is how the numbers above were
measured and how to measure them again if Minecraft's font ever changes.

## Licence

MIT. Nothing in here comes from anywhere else: the glyphs, the arrows and the icon are all drawn by
`tools/`.
