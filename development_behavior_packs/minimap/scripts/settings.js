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
	size: 9,         // cells across
	zoom: 2,         // blocks per cell
	rotate: false,   // false keeps north up and turns the arrow instead
	entities: true,
	coords: false,
	right: 88,       // spaces in front of every line
	up: 30,          // empty lines after the map
};

export const SIZES = [7, 9, 11, 13, 15];
export const ZOOMS = [1, 2, 4, 8];
export const LIMITS = { right: [0, 240], up: [0, 60] };
export const STEP = { right: 4, up: 2 };

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
	settings.size = nearest(SIZES, settings.size);
	settings.zoom = nearest(ZOOMS, settings.zoom);
	settings.right = clamped("right", settings.right);
	settings.up = clamped("up", settings.up);
	cache.set(player.id, settings);
	return settings;
}

/** Writes the changed settings back to the player and to the cache. */
export function save(player, changes) {
	const settings = { ...settingsOf(player), ...changes };
	settings.right = clamped("right", settings.right);
	settings.up = clamped("up", settings.up);
	cache.set(player.id, settings);
	for (const [key, value] of Object.entries(changes)) {
		player.setDynamicProperty(`minimap:${key}`, key in LIMITS ? clamped(key, value) : value);
	}
	return settings;
}

/** Moves the map one step in one direction, which is what the arrows in the menu do. */
export function nudge(player, key, steps) {
	return save(player, { [key]: settingsOf(player)[key] + steps * STEP[key] });
}

/** The next size or zoom up or down its list, stopping at the ends. */
export function step(player, key, direction) {
	const list = key === "size" ? SIZES : ZOOMS;
	const at = list.indexOf(settingsOf(player)[key]);
	return save(player, { [key]: list[Math.min(list.length - 1, Math.max(0, at + direction))] });
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
