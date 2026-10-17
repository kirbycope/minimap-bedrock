// Turns the blocks around a player into the title the HUD draws the map from.
//
// The resource pack's ui/hud_screen.json is a grid of image controls, one per map cell, and each shows
// the texture its two characters of the title name. So the grid is built here as values, and written
// out a row at a time as hex, fixed width, in the layout tools/hud.py sets down in hud_layout.js.

import { ARROWS, BORDER, HOSTILE, ITEM, PASSIVE, PLAYER, SHADES, UNKNOWN } from "./palette.js";
import { world } from "@minecraft/server";
import { CHUNK, CHUNKS, COLUMNS, HEAD_MARKER, INFO, INFO_WIDTH, MARKER, NO_CELL, SIZES } from "./hud_layout.js";
import { columnAt, layerFor } from "./terrain.js";

const BRIGHT = 1;          // the brightness step for ground level with, or above, what lies north of it
const DARK = 0;
const MAX_ENTITIES = 64;   // drawn per map, so a mob farm cannot make the map the expensive part
const NONE = -1;           // a cell outside a round map, drawn as nothing

/** The map for one player, as the titles to send them: the header first, then a title per CHUNK rows. */
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

	// the grid as values, framed: a square with a cell of frame all round, or a disc ringed by frame
	const grid = new Array(span * span).fill(BORDER * SHADES + BRIGHT);
	for (let row = 0; row < size; row++) {
		for (let column = 0; column < size; column++) {
			const at = row * size + column;
			grid[(row + 1) * span + column + 1] = colour[at] * SHADES + shade[at];
		}
	}
	if (settings.shape === "circle") {
		const middle = span / 2;
		for (let row = 0; row < span; row++) {
			for (let column = 0; column < span; column++) {
				const distance = Math.hypot(row + 0.5 - middle, column + 0.5 - middle);
				if (distance > middle) grid[row * span + column] = NONE;
				else if (distance > middle - 1) grid[row * span + column] = BORDER * SHADES + BRIGHT;
			}
		}
	}

	// the arrow and the letters are images of their own over the cells, so they only need saying which:
	// the letter for the top edge, then right, bottom and left, clockwise round the compass
	const top = settings.rotate ? Math.round(turned(yaw + 180) / 90) % 4 : 0;
	const letters = [0, 1, 2, 3].map((edge) => (top + edge) % 4).join("");
	const arrow = settings.rotate ? 0 : pointing(yaw);
	const head = HEAD_MARKER + SIZES.indexOf(size) + arrow + letters + lines(player, settings, SIZES.indexOf(size));
	// the right-hand cell first, because the HUD anchors the map by its top right corner
	const rows = [];
	for (let row = 0; row < span; row++) {
		let line = "";
		for (let cell = 0; cell < COLUMNS; cell++) line += cell < span ? hex(grid[row * span + span - 1 - cell]) : NO_CELL;
		rows.push(line);
	}
	return [head, ...chunks(rows)];
}

/** The rows as chunk titles, each with its marker; a chunk past the map's last row goes empty. */
function chunks(rows) {
	const titles = [];
	for (let chunk = 0; chunk < CHUNKS; chunk++) {
		titles.push(`${MARKER}r${String(chunk).padStart(2, "0")}` + rows.slice(chunk * CHUNK, chunk * CHUNK + CHUNK).join(""));
	}
	return titles;
}

/** The title that takes the map off the screen. */
export function hidden() {
	return [HEAD_MARKER + "-0123" + "-".repeat(INFO) + " ".repeat(INFO * INFO_WIDTH), ...chunks([])];
}

/** The lines under the map, as Xaero's minimap has them: which are on, as the map's size for a line that
is and "-" for one that is not, then whichever they are, in this order, each padded to INFO_WIDTH. */
function lines(player, settings, sizeIndex) {
	const at = player.location;
	const feet = { x: Math.floor(at.x), y: Math.floor(at.y), z: Math.floor(at.z) };
	const shown = [];
	// a line must not start with a number: JSON UI reads "   12, 64, -3" as the number 12 and shows nothing
	if (settings.coords) shown.push(`XYZ: ${feet.x}, ${feet.y}, ${feet.z}`);
	if (settings.angle) {
		const { x: pitch, y: yaw } = player.getRotation();
		shown.push(`${COMPASS[Math.round(turned(yaw + 180) / 45) % 8]} ${yaw.toFixed(1)} / ${pitch.toFixed(1)}`);
	}
	if (settings.biome) shown.push(ask(() => named(player.dimension.getBiome(feet).id)));
	if (settings.light) {
		shown.push(ask(() => `Light: ${player.dimension.getLightLevel(feet)} (sky ${player.dimension.getSkyLightLevel(feet)})`));
	}
	if (settings.time) shown.push(clock());
	let text = "";
	for (let line = 0; line < INFO; line++) text += line < shown.length ? sizeIndex : "-";
	for (let line = 0; line < INFO; line++) text += (shown[line] ?? "").slice(0, INFO_WIDTH).padStart(INFO_WIDTH);
	return text;
}

const COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];

/** A reading the game may refuse, an unloaded block or an API a version lacks, as nothing rather than an error. */
function ask(read) {
	try {
		return read();
	} catch {
		return "";
	}
}

/** "minecraft:dark_forest" as "Dark Forest". */
function named(id) {
	return id.replace(/^.*:/, "").split("_").map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(" ");
}

/** The day and the hour, the way a clock in the game would read: tick 0 is six in the morning. */
function clock() {
	const ticks = world.getTimeOfDay();
	const hours = (Math.floor(ticks / 1000) + 6) % 24;
	const minutes = Math.floor(((ticks % 1000) * 60) / 1000);
	return `Day ${world.getDay()}, ${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

/** A value's two letters, its hex digits written a to p: JSON UI reads a slice made only of digits as a
number, so "03" would become 3 and name no texture. tools/palette.py names the textures the same way. */
function hex(value) {
	if (value === NONE) return NO_CELL;
	return String.fromCharCode(97 + (value >> 4), 97 + (value & 15));
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

/** Which of the arrows to draw when north stays at the top of the map. */
function pointing(yaw) {
	return Math.round(turned(yaw - 180) / (360 / ARROWS)) % ARROWS;
}

/** An angle in degrees brought back into 0 to 360, whatever it started as. */
function turned(degrees) {
	return ((degrees % 360) + 360) % 360;
}
