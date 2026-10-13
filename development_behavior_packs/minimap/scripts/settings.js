// What each player has chosen, kept on the player so it survives a rejoin.
//
// Dynamic properties are read far more often than they are written, so a player's settings are read
// once into a cache and the cache is what the tick loop asks.

// Where the map sits is two numbers rather than a corner, because an add-on cannot ask how big the
// screen is. Minecraft centres the action bar's text and anchors it a fixed distance above the hotbar,
// so spaces in front of a line slide the map right and empty lines under the map slide it up. The
// defaults put it in the top right corner of a 1920x1200 screen at the interface size Minecraft picks
// for it; on a smaller screen the map starts lower and further in, and the arrows in the menu move it.
const DEFAULTS = {
	on: true,
	size: 16,        // cells across, a multiple of four so the player sits on one line of text
	zoom: 2,         // blocks per cell
	rotate: false,   // false keeps north up and turns the arrow instead
	entities: true,
	coords: false,
	right: 88,       // spaces in front of every line
	up: 30,          // empty lines after the map
};

// Multiples of four, because a character holds two rows and the player's own four cells have to fall
// on one of them. A cell is five pixels, so sixteen across is ninety pixels of screen with the frame.
export const SIZES = [8, 12, 16, 20, 24, 32, 40];
export const ZOOMS = [1, 2, 4, 8];
// The smaller Minecraft draws its interface, the more of these it takes to reach a corner, so the
// range has to cover the smallest interface size as well as the largest.
// How far from the player the map may ask about, in blocks. The game only answers for chunks near the
// player, and while you are moving the ground ahead has not arrived yet, so a map that reaches further
// than this draws black however long you wait. Size times zoom is what reaches: a map of 24 cells at 4
// blocks a cell looks 48 blocks out. The menu stops at the combinations that fit.
export const REACH = 48;

export const LIMITS = { right: [0, 600], up: [0, 200] };
export const STEP = { right: 8, up: 4 };

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
 * not one of SIZES would land the player's own cells across two lines of text and the map would throw
 * rather than draw. /scriptevent minimap:set takes whatever is typed, so this is where that is caught.
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
	settings.right = clamped("right", settings.right);
	settings.up = clamped("up", settings.up);
	for (const key of ["on", "rotate", "entities", "coords"]) settings[key] = Boolean(settings[key]);
	return settings;
}

/** Moves the map one step in one direction, which is what the arrows in the menu do. */
export function nudge(player, key, steps) {
	return save(player, { [key]: settingsOf(player)[key] + steps * STEP[key] });
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

function clamped(key, value) {
	const [low, high] = LIMITS[key];
	return Math.min(high, Math.max(low, Math.round(Number(value) || 0)));
}

/** The allowed value closest to one that is out of date or came from a hand-edited property. */
function nearest(allowed, value) {
	let best = allowed[0];
	for (const option of allowed) {
		if (Math.abs(option - value) < Math.abs(best - value)) best = option;
	}
	return best;
}
