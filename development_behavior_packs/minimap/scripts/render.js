// Turns the blocks around a player into the line of text that is the map.
//
// One character of the map is one column and TWO rows: the pack's font has a glyph for every pair of
// colours that can sit one above the other, which is what gets the map down to five screen pixels a
// block. See tools/palette.py. So the grid is built first, as values, and only then turned into text
// two rows at a time.

import {
	ARROW, BORDER, GLYPH_OVERLAY, GLYPH_TERRAIN, HOSTILE, ITEM, LETTER_N, PASSIVE, PLAYER, SHADES,
	UNKNOWN, VALUES,
} from "./palette.js";
import { columnAt, layerFor } from "./terrain.js";

const BRIGHT = 1;          // the brightness step for ground level with, or above, what lies north of it
const DARK = 0;
const MAX_ENTITIES = 64;   // drawn per map, so a mob farm cannot make the map the expensive part
const CARDINALS = ["n", "e", "s", "w"];
const MARKER = -1;         // a grid cell covered by the arrow or the heading letter instead of terrain

/** The map for one player, as the text to put in their action bar. */
export function draw(player, settings, tick) {
	const { size, zoom } = settings;
	const span = size + 2;     // the frame is a cell on every side
	const dimension = player.dimension;
	const layer = layerFor(player);
	const origin = player.location;
	const px = Math.floor(origin.x);
	const pz = Math.floor(origin.z);
	const yaw = player.getRotation().y;
	const view = settings.rotate ? facing(yaw) : { rx: 1, rz: 0, fx: 0, fz: -1 };

	// the grid, read out of the terrain cache, with the columns this pass can afford sampled on the way
	const colour = new Array(size * size);
	const height = new Array(size * size);
	for (let row = 0; row < size; row++) {
		for (let column = 0; column < size; column++) {
			// the player stands at the middle of the four cells in the centre, so the offsets are halves
			const sx = column - size / 2 + 0.5;
			const sy = row - size / 2 + 0.5;
			const x = px + Math.round((view.rx * sx + view.fx * -sy) * zoom);
			const z = pz + Math.round((view.rz * sx + view.fz * -sy) * zoom);
			const cell = columnAt(dimension, layer, x, z, tick);
			const at = row * size + column;
			colour[at] = cell === undefined ? UNKNOWN : cell.c;
			height[at] = cell === undefined ? undefined : cell.y;
		}
	}

	// Minecraft's own map shading: a cell is the darker step when it is lower than the cell beyond it,
	// which is what turns a field of colour into hills
	const shade = new Array(size * size).fill(BRIGHT);
	for (let row = 1; row < size; row++) {
		for (let column = 0; column < size; column++) {
			const at = row * size + column;
			const behind = height[at - size];
			if (height[at] === undefined || behind === undefined) continue;
			if (height[at] < behind) shade[at] = DARK;
		}
	}

	if (settings.entities) blips(player, colour, settings, view);

	// the grid as values, framed, then the two markers over it
	const grid = new Array(span * span).fill(BORDER * SHADES + BRIGHT);
	for (let row = 0; row < size; row++) {
		for (let column = 0; column < size; column++) {
			const at = row * size + column;
			grid[(row + 1) * span + column + 1] = colour[at] * SHADES + shade[at];
		}
	}

	const heading = settings.rotate ? CARDINALS[Math.round(turned(yaw + 180) / 90) % 4] : "n";
	const letter = GLYPH_OVERLAY + LETTER_N + CARDINALS.indexOf(heading) * 2;
	const arrow = GLYPH_OVERLAY + ARROW + (settings.rotate ? 0 : pointing(yaw)) * 2;
	// a marker is two characters wide and one tall, so it covers two columns and the two rows of one
	// line. Sizes are multiples of four, which is what puts the player's own four cells on one line.
	const markers = [[0, span / 2 - 1, letter], [span / 2 - 1, span / 2 - 1, arrow]];
	for (const [row, column] of markers) {
		for (const cell of [row * span + column, row * span + column + 1,
			(row + 1) * span + column, (row + 1) * span + column + 1]) grid[cell] = MARKER;
	}

	const lines = [];
	if (settings.coords) lines.push(`${Math.floor(origin.x)}, ${Math.floor(origin.y)}, ${Math.floor(origin.z)}`);
	for (let row = 0; row < span; row += 2) {
		let line = "";
		for (let column = 0; column < span; column++) {
			const top = grid[row * span + column];
			if (top !== MARKER) {
				line += String.fromCharCode(GLYPH_TERRAIN + top * VALUES + grid[(row + 1) * span + column]);
				continue;
			}
			const marker = markers.find((m) => m[0] === row && (m[1] === column || m[1] + 1 === column));
			line += String.fromCharCode(marker[2] + (column - marker[1]));
		}
		lines.push(line);
	}

	// Spaces in front of a line push the map right and empty lines after it push the map up, because
	// Minecraft centres this text and anchors it above the hotbar. See settings.js.
	const pad = " ".repeat(settings.right);
	const padded = lines.map((line) => pad + line);
	for (let blank = 0; blank < settings.up; blank++) padded.push(" ");
	return padded.join("\n");
}

/** Mobs, players and dropped items, over the terrain they are standing on. */
function blips(player, colour, settings, view) {
	const { size, zoom } = settings;
	const reach = (size / 2 + 0.5) * zoom;
	let entities;
	try {
		entities = player.dimension.getEntities({
			location: player.location,
			maxDistance: Math.ceil(reach * 1.5),
		});
	} catch {
		return;
	}
	let drawn = 0;
	for (const entity of entities) {
		if (drawn >= MAX_ENTITIES) break;
		if (entity.id === player.id) continue;
		const dx = entity.location.x - player.location.x;
		const dz = entity.location.z - player.location.z;
		const sx = Math.round((dx * view.rx + dz * view.rz) / zoom + size / 2 - 0.5);
		const sy = Math.round(-(dx * view.fx + dz * view.fz) / zoom + size / 2 - 0.5);
		if (sx < 0 || sx >= size || sy < 0 || sy >= size) continue;
		colour[sy * size + sx] = kind(entity);
		drawn += 1;
	}
}

function kind(entity) {
	if (entity.typeId === "minecraft:player") return PLAYER;
	if (entity.typeId === "minecraft:item" || entity.typeId === "minecraft:xp_orb") return ITEM;
	try {
		return entity.matches({ families: ["monster"] }) ? HOSTILE : PASSIVE;
	} catch {
		return PASSIVE;
	}
}

/** The way the player faces, as the map's right and forward in world x and z. */
function facing(yaw) {
	const radians = (yaw * Math.PI) / 180;
	return {
		rx: -Math.cos(radians), rz: -Math.sin(radians),
		fx: -Math.sin(radians), fz: Math.cos(radians),
	};
}

/** Which of the eight arrows to draw when north stays at the top of the map. */
function pointing(yaw) {
	return Math.round(turned(yaw - 180) / 45) % 8;
}

/** An angle in degrees brought back into 0 to 360, whatever it started as. */
function turned(degrees) {
	return ((degrees % 360) + 360) % 360;
}

/**
 * A ruler for the font: pairs of known colours in a block, then a line of ordinary text. Measuring this
 * in a screenshot is how the cell size and the spacing were found, and how to find them again when
 * Minecraft's font changes.
 */
export function calibration() {
	const a = PLAYER * SHADES + BRIGHT;
	const b = HOSTILE * SHADES + BRIGHT;
	const lines = [];
	for (let row = 0; row < 4; row++) {
		let line = "";
		for (let column = 0; column < 8; column++) {
			const top = (row + column) % 2 === 0 ? a : b;
			line += String.fromCharCode(GLYPH_TERRAIN + top * VALUES + (top === a ? b : a));
		}
		lines.push(line);
	}
	lines.push(String.fromCharCode(GLYPH_OVERLAY + ARROW) + String.fromCharCode(GLYPH_OVERLAY + ARROW + 1));
	lines.push("0123456789");
	return lines.join("\n");
}
