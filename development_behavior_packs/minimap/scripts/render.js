// Turns the blocks around a player into the line of text that is the map.
//
// Every cell is one character from the pack's own font page, where each glyph is a solid square of
// colour, so a row of cells is a row of pixels and the newline between rows is the next scanline.

import {
	ARROW, BORDER, GLYPH_OVERLAY, GLYPH_TERRAIN, HOSTILE, ITEM, LETTER_N, PASSIVE, PLAYER, SHADES, UNKNOWN,
} from "./palette.js";
import { columnAt, layerFor } from "./terrain.js";

const FLAT = 2;            // the brightness step for ground level with what lies north of it
const MAX_ENTITIES = 48;   // drawn per map, so a mob farm cannot make the map the expensive part
const CARDINALS = ["n", "e", "s", "w"];

/** The map for one player, as the text to put in their action bar. */
export function draw(player, settings, tick) {
	const { size, zoom } = settings;
	const half = (size - 1) / 2;
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
			const sx = column - half;
			const sy = row - half;
			const x = px + Math.round((view.rx * sx + view.fx * -sy) * zoom);
			const z = pz + Math.round((view.rz * sx + view.fz * -sy) * zoom);
			const cell = columnAt(dimension, layer, x, z, tick);
			const at = row * size + column;
			colour[at] = cell === undefined ? UNKNOWN : cell.c;
			height[at] = cell === undefined ? undefined : cell.y;
		}
	}

	// Minecraft's own map shading: a cell is brighter than the one beyond it and darker than the one
	// in front, which is what turns a field of colour into hills
	const shade = new Array(size * size).fill(FLAT);
	for (let row = 1; row < size; row++) {
		for (let column = 0; column < size; column++) {
			const at = row * size + column;
			const behind = height[at - size];
			if (height[at] === undefined || behind === undefined) continue;
			const step = height[at] - behind;
			shade[at] = step > 0 ? 3 : step === 0 ? FLAT : step > -4 ? 1 : 0;
		}
	}

	if (settings.entities) blips(player, colour, settings, half, view);
	colour[half * size + half] = -1;   // the player's own cell, drawn as the arrow below

	// a frame a cell wide on every side, so the map reads against any ground, with which way is up in
	// the middle of its top edge and the player's arrow in the middle of the map
	const heading = settings.rotate ? CARDINALS[Math.round(turned(yaw + 180) / 90) % 4] : "n";
	const frame = String.fromCharCode(GLYPH_TERRAIN + BORDER * SHADES + 3);
	const letter = String.fromCharCode(GLYPH_OVERLAY + LETTER_N + CARDINALS.indexOf(heading));
	const arrow = String.fromCharCode(GLYPH_OVERLAY + ARROW + (settings.rotate ? 0 : pointing(yaw)));

	// Spaces in front of a line push the map right and empty lines after it push the map up, because
	// Minecraft centres this text and anchors it above the hotbar. See settings.js.
	const pad = " ".repeat(settings.right);
	const lines = [];
	if (settings.coords) lines.push(pad + `${Math.floor(origin.x)}, ${Math.floor(origin.y)}, ${Math.floor(origin.z)}`);
	lines.push(pad + frame.repeat(half + 1) + letter + frame.repeat(size - half));
	for (let row = 0; row < size; row++) {
		let line = pad + frame;
		for (let column = 0; column < size; column++) {
			const at = row * size + column;
			line += colour[at] === -1 ? arrow : String.fromCharCode(GLYPH_TERRAIN + colour[at] * SHADES + shade[at]);
		}
		lines.push(line + frame);
	}
	lines.push(pad + frame.repeat(size + 2));
	for (let blank = 0; blank < settings.up; blank++) lines.push(" ");
	return lines.join("\n");
}

/** Mobs, players and dropped items, over the terrain they are standing on. */
function blips(player, colour, settings, half, view) {
	const { size, zoom } = settings;
	const reach = (half + 0.5) * zoom;
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
		const sx = Math.round((dx * view.rx + dz * view.rz) / zoom);
		const sy = Math.round(-(dx * view.fx + dz * view.fz) / zoom);
		const column = sx + half;
		const row = sy + half;
		if (column < 0 || column >= size || row < 0 || row >= size) continue;
		colour[row * size + column] = kind(entity);
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
 * A ruler for the font: eight rows of eight cells that alternate between two colours, then a row of the
 * terrain colours. Measuring this in a screenshot is how the cell size and the space between rows were
 * found, and it is how they can be found again when Minecraft's own font changes.
 */
export function calibration() {
	const a = String.fromCharCode(GLYPH_TERRAIN + PLAYER * SHADES + 3);
	const b = String.fromCharCode(GLYPH_TERRAIN + HOSTILE * SHADES + 3);
	const lines = [];
	for (let row = 0; row < 8; row++) {
		let line = "";
		for (let column = 0; column < 8; column++) line += (row + column) % 2 === 0 ? a : b;
		lines.push(line);
	}
	lines.push(String.fromCharCode(GLYPH_OVERLAY + ARROW) + String.fromCharCode(GLYPH_OVERLAY + LETTER_N) + a + b);
	lines.push("0123456789");
	return lines.join("\n");
}
