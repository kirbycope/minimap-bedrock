// The map's memory: what the topmost block of each column is, and what colour that makes the cell.
//
// Asking the world for a column costs a block lookup, and a map is hundreds of columns, so nothing is
// sampled twice. A column is remembered until a player changes a block there or it goes stale, and only
// a few columns are sampled per pass, which is what keeps a 21x21 map off the server's tick budget.

import { world } from "@minecraft/server";
import { BLOCKS, DYED, DYES, KEYWORDS, UNKNOWN } from "./palette.js";

const BUDGET = 64;         // columns sampled per pass, shared by every player
const STALE = 1200;        // ticks before a column is sampled again, so growth and flowing water show up
const LAYERS = 8;          // how many dimension-and-height maps to keep before the oldest goes
const COLUMNS = 8192;      // columns per layer

const layers = new Map();  // "dimension|layer" -> Map("x,z" -> { y, c, t })
const colours = new Map(); // block type id -> colour index
let left = 0;              // what is still in this pass's budget

/** Starts a pass. Everything sampled after this shares one budget. */
export function beginPass() {
	left = BUDGET;
}

/**
 * Where to sample from, and which map to remember it in.
 *
 * Above ground that is the sky, so every player on the surface shares one map. Under a roof it is the
 * player's own height, rounded to a band of four, so a cave reads as the level you are standing on
 * rather than as the stone above it. The Nether's bedrock roof puts a player there in a band as well.
 */
export function layerFor(player) {
	const dimension = player.dimension;
	const feet = Math.floor(player.location.y);
	const covered = roofed(player, feet);
	if (!covered) return { id: `${dimension.id}|sky`, ceiling: undefined };
	const band = Math.floor((feet + 2) / 4);
	return { id: `${dimension.id}|${band}`, ceiling: band * 4 + 3 };
}

/**
 * The cell for one column: its colour index and the height of its top block, or undefined when the
 * chunk is not loaded or this pass has sampled all it is allowed to.
 */
export function columnAt(dimension, layer, x, z, tick) {
	const map = mapFor(layer.id);
	const key = `${x},${z}`;
	const known = map.get(key);
	if (known && tick - known.t < STALE) return known;
	if (left <= 0) return known;
	left -= 1;
	const block = sample(dimension, x, z, layer.ceiling);
	if (block === undefined) return known;
	const fresh = { y: block.y, c: colourFor(block.typeId), t: tick };
	map.set(key, fresh);
	if (map.size > COLUMNS) {
		for (const old of map.keys()) {
			map.delete(old);
			if (map.size <= COLUMNS * 0.75) break;
		}
	}
	return fresh;
}

/** Forgets a column, so the next pass sees what was built or broken there. */
export function forgetColumn(dimension, x, z) {
	for (const [id, map] of layers) {
		if (id.startsWith(`${dimension.id}|`)) map.delete(`${x},${z}`);
	}
}

/** The colour index for a block, worked out once per block type and remembered. */
export function colourFor(typeId) {
	const known = colours.get(typeId);
	if (known !== undefined) return known;
	colours.set(typeId, work(typeId));
	return colours.get(typeId);
}

function work(typeId) {
	const exact = BLOCKS[typeId];
	if (exact !== undefined) return exact;
	const name = typeId.startsWith("minecraft:") ? typeId.slice(10) : typeId;
	if (DYED.some((family) => name.includes(family))) {
		// the dye words are in order, so light_blue is tried before blue and light_gray before gray
		for (const [dye, colour] of Object.entries(DYES)) {
			if (name.includes(dye)) return colour;
		}
	}
	for (const [needle, colour] of KEYWORDS) {
		if (name.includes(needle)) return colour;
	}
	return UNKNOWN;
}

/** Whether something solid is overhead. Water is not a roof, so swimming still shows the coastline. */
function roofed(player, feet) {
	try {
		const over = player.dimension.getBlockAbove({ x: Math.floor(player.location.x), y: feet + 1, z: Math.floor(player.location.z) },
			{ maxDistance: 64, includeLiquidBlocks: false, includePassableBlocks: false });
		return over !== undefined;
	} catch {
		return false;
	}
}

function sample(dimension, x, z, ceiling) {
	try {
		return dimension.getTopmostBlock({ x, z }, ceiling);
	} catch {
		return undefined;   // an unloaded chunk, which the caller draws as not yet mapped
	}
}

function mapFor(id) {
	let map = layers.get(id);
	if (map === undefined) {
		map = new Map();
		layers.set(id, map);
		if (layers.size > LAYERS) layers.delete(layers.keys().next().value);
	}
	return map;
}

world.afterEvents.playerPlaceBlock.subscribe((event) => {
	forgetColumn(event.dimension, event.block.x, event.block.z);
});

world.afterEvents.playerBreakBlock.subscribe((event) => {
	forgetColumn(event.dimension, event.block.x, event.block.z);
});
