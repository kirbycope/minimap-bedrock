# Credits

## The add-on

Nothing shipped inside the `.mcaddon` comes from anywhere else. The glyph pages, the player and compass
arrows, the colour table and both pack icons are drawn by [tools/palette.py](tools/palette.py) and
[tools/pack_icon.py](tools/pack_icon.py). The colours those tools write are Minecraft's own map colours,
which the game draws a map in your hand with.

## The project art

The title on `assets/thumbnail.png` is set in **Passion One** (Black), by **Dario Manuel Muhafara**,
under the SIL Open Font License 1.1.

- Project: <https://fonts.google.com/specimen/Passion+One>
- Licence: OFL-1.1
- In this tree: [tools/fonts/PassionOne-Black.ttf](tools/fonts/PassionOne-Black.ttf)

The font is used only to draw the thumbnail. It is not part of either pack and is not in the
`.mcaddon`.

Everything else in the thumbnail is this project's own: `assets/background.png` is a screenshot of the
add-on running, and `assets/skin.png` is the author's player skin.

## Code reused from this author's other repositories

These came from `skyblock-infinite-bedrock`, which took the first two from `cobblemon-bedrock`:

- [tools/bridge.py](tools/bridge.py), which runs commands through the MCP bridge
- [tools/client_drive.py](tools/client_drive.py), which drives the real client and captures what it shows
- [tools/skin_render.py](tools/skin_render.py), which renders the posed player from a 64x64 skin
- [tools/make_preview.py](tools/make_preview.py) and [tools/tinyify.py](tools/tinyify.py)
- the type and effect half of [tools/make_thumbnail.py](tools/make_thumbnail.py); its scene is this
  project's own
