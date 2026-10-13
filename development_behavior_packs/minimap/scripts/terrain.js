// The map's memory: what the topmost block of each column is, and what colour that makes the cell.
//
// Asking the world for a column costs a block lookup, and a map is hundreds of columns, so nothing is
// sampled twice. A column is remembered until a player changes a block there or it goes stale, and only
// a few columns are sampled per pass, which is what keeps a 21x21 map off the server's tick budget.

import { world } from "@minecraft/server";
import { BLOCKS, DYED, DYES, KEYWORDS, UNKNOWN } from "./palette.js";

// Columns sampled per pass, shared by every player. A fixed sixty-four filled a small map in a blink
// and left a big one black for ever: a forty cell map is sixteen hundred columns, and flying turns all
// of them over at once. The budget follows the biggest map being drawn instead, so any size fills in
// about the same handful of passes, and the ceiling is what keeps the cost off the server's tick.
const BUDGET_LOW = 64;
const BUDGET_HIGH = 160;
const PASSES_TO_FILL = 10;
const STALE = 1200;        // ticks before a column is sampled again, so growth and flowing water show up
const RETRY = 40;          // ticks before a column outside the loaded chunks is asked for again
const MISS = -1;           // a column the game would not answer for
const LAYERS = 8;          // how many dimension-and-height maps to keep before the oldest goes
const COLUMNS = 8192;      // columns per layer

const layers = new Map();  // "dimension|layer" -> Map("x,z" -> { y, c, t })
const colours = new Map(); // block type id -> colour index
let left = 0;              // what is still in this pass's budget

/**
 * Starts a pass. Everything sampled after this shares one budget, which is set by the largest map
 * about to be drawn: cells is that map's column count.
 */
export function beginPass(cells) {
	left = Math.max(BUDGET_LOW, Math.min(BUDGET_HIGH, Math.ceil(cells / PASSES_TO_FILL)));
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
	if (known && tick - known.t < STALE) return known.c === MISS ? undefined : known;
	if (left <= 0) return known === undefined || known.c === MISS ? undefined : known;
	left -= 1;
	const block = sample(dimension, x, z, layer.ceiling);
	const fresh = block === undefined ? undefined : read(dimension, block, tick);
	if (fresh === undefined) {
		// The game only answers for chunks near the player, so a wide map asks for ground that is not
		// there. Remembering the refusal for a few seconds keeps those columns from eating the pass's
		// whole budget and starving the ones it could have drawn.
		map.set(key, { y: undefined, c: MISS, t: tick - STALE + RETRY });
		return undefined;
	}
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

/**
 * The liquid standing on a block, if there is any.
 *
 * getTopmostBlock answers with the highest block that is neither air nor liquid, so without this an
 * ocean draws as its floor and a river as its bed. One more block read per column settles it: what
 * sits directly on the ground is the water or the lava, when there is some.
 */
function over(dimension, block) {
	try {
		const above = dimension.getBlock({ x: block.x, y: block.y + 1, z: block.z });
		const id = above === undefined ? undefined : above.typeId;
		return id === "minecraft:water" || id === "minecraft:flowing_water"
			|| id === "minecraft:lava" || id === "minecraft:flowing_lava" ? id : undefined;
	} catch {
		return undefined;
	}
}

/**
 * What a sampled block is, as a height and a colour.
 *
 * A Block is a handle into a chunk rather than a copy of it, so reading its height or its type can
 * throw later even though the call that returned it did not: fly fast enough and the chunk is gone by
 * the time the column is read. That is the one error this add-on ever logged in play. A column that
 * does this is simply left unsampled, and the next pass picks it up.
 */
function read(dimension, block, tick) {
	try {
		return { y: block.y, c: colourFor(over(dimension, block) ?? block.typeId), t: tick };
	} catch {
		return undefined;
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
