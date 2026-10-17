// What each player has chosen, kept on the player so it survives a rejoin.
//
// Dynamic properties are read far more often than they are written, so a player's settings are read
// once into a cache and the cache is what the tick loop asks.

import { SIZES } from "./hud_layout.js";

// The map sits in the top right corner on every screen: the resource pack's HUD layer anchors it there,
// so there is no position to keep.
const DEFAULTS = {
	on: true,
	size: 16,        // cells across, one of SIZES
	zoom: 2,         // blocks per cell
	rotate: false,   // false keeps north up and turns the arrow instead
	entities: true,
	coords: false,   // the lines under the map, as Xaero's minimap has them
	angle: false,
	biome: false,
	light: false,
	time: false,
	shape: "square",  // or "circle", as Xaero's minimap offers
};

export const SHAPES = ["square", "circle"];
// the lines of text under the map, in the order they are drawn
export const LINES = ["coords", "angle", "biome", "light", "time"];

export const ZOOMS = [1, 2, 4, 8];
// How far from the player the map may ask about, in blocks. The game only answers for chunks near the
// player, and while you are moving the ground ahead has not arrived yet, so a map that reaches further
// than this draws black however long you wait. Size times zoom is what reaches: a map of 24 cells at 4
// blocks a cell looks 48 blocks out. The menu stops at the combinations that fit.
export const REACH = 48;

const cache = new Map();   // player id -> settings

/** The player's settings, read from the player the first time and held after that. */
export function settingsOf(player) {
	let settings = cache.get(player.id);
	if (settings) return settings;
	settings = { ...DEFAULTS };
	for (const key of Object.keys(DEFAULTS)) {
		const stored = player.getDynamicProperty(`minimap:${key}`);
		if (stored !== undefined) settings[key] = stored;
	}
	cache.set(player.id, checked(settings));
	return settings;
}

/**
 * Writes the changed settings back to the player and to the cache.
 *
 * Everything is put through the same checks as a setting read off the player, because a size that is
 * not one of SIZES has no place in the map title and the HUD would draw no arrow for it. /scriptevent minimap:set takes whatever is typed, so this is where that is caught.
 */
export function save(player, changes) {
	const settings = checked({ ...settingsOf(player), ...changes });
	cache.set(player.id, settings);
	for (const key of Object.keys(changes)) {
		player.setDynamicProperty(`minimap:${key}`, settings[key]);
	}
	return settings;
}

/** Whether a map that size at that zoom stays inside the ground the game will answer for. */
export function fits(size, zoom) {
	return (size / 2) * zoom <= REACH;
}

/** A settings object with every number brought back to one the renderer can draw. */
function checked(settings) {
	settings.size = nearest(SIZES, settings.size);
	settings.zoom = nearest(ZOOMS, settings.zoom);
	while (!fits(settings.size, settings.zoom) && settings.zoom > ZOOMS[0]) {
		settings.zoom = ZOOMS[ZOOMS.indexOf(settings.zoom) - 1];
	}
	while (!fits(settings.size, settings.zoom) && settings.size > SIZES[0]) {
		settings.size = SIZES[SIZES.indexOf(settings.size) - 1];
	}
	for (const key of ["on", "rotate", "entities", ...LINES]) settings[key] = Boolean(settings[key]);
	if (!SHAPES.includes(settings.shape)) settings.shape = DEFAULTS.shape;
	return settings;
}

/** The next size or zoom up or down its list, stopping at the ends. */
export function step(player, key, direction) {
	const settings = settingsOf(player);
	const list = key === "size" ? SIZES : ZOOMS;
	const at = list.indexOf(settings[key]);
	const next = list[Math.min(list.length - 1, Math.max(0, at + direction))];
	const other = key === "size" ? settings.zoom : settings.size;
	// growing past what the game will answer for would only add black, so the button stops there
	if (direction > 0 && !fits(key === "size" ? next : other, key === "zoom" ? next : other)) return settings;
	return save(player, { [key]: next });
}

export function forget(playerId) {
	cache.delete(playerId);
}

/** The allowed value closest to one that is out of date or came from a hand-edited property. */
function nearest(allowed, value) {
	let best = allowed[0];
	for (const option of allowed) {
		if (Math.abs(option - value) < Math.abs(best - value)) best = option;
	}
	return best;
}
