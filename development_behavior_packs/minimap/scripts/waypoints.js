// Waypoints and the deathpoint, as Xaero's minimap keeps them: each player's own, saved on the player.
//
// A waypoint is a named, coloured spot in one dimension. The deathpoint is where the player last died,
// kept until the next death, so the way back to the dropped items is on the map.

import { world } from "@minecraft/server";

const WAYPOINTS = "minimap:waypoints";
const DEATH = "minimap:death";
export const MAX_WAYPOINTS = 32;   // a dynamic property holds 32767 characters, and the menu has to list them

const cache = new Map();   // player id -> { waypoints: [...], death }

function stored(player) {
	let entry = cache.get(player.id);
	if (entry) return entry;
	entry = { waypoints: read(player, WAYPOINTS, []), death: read(player, DEATH, undefined) };
	if (!Array.isArray(entry.waypoints)) entry.waypoints = [];
	cache.set(player.id, entry);
	return entry;
}

/** A JSON dynamic property, or the fallback when it is missing or someone hand-edited it into nonsense. */
function read(player, key, fallback) {
	try {
		const text = player.getDynamicProperty(key);
		return typeof text === "string" ? JSON.parse(text) : fallback;
	} catch {
		return fallback;
	}
}

/** The player's waypoints, as { name, colour, x, y, z, dimension }. */
export function waypointsOf(player) {
	return stored(player).waypoints;
}

/** Where the player last died, as { x, y, z, dimension }, or undefined. */
export function deathOf(player) {
	return stored(player).death;
}

/** A waypoint where the player stands. Returns false when the list is full. */
export function addWaypoint(player, name, colour) {
	const entry = stored(player);
	if (entry.waypoints.length >= MAX_WAYPOINTS) return false;
	const { x, y, z } = player.location;
	entry.waypoints.push({
		name: name.trim().slice(0, 24) || `Waypoint ${entry.waypoints.length + 1}`,
		colour,
		x: Math.floor(x), y: Math.floor(y), z: Math.floor(z),
		dimension: player.dimension.id,
	});
	player.setDynamicProperty(WAYPOINTS, JSON.stringify(entry.waypoints));
	return true;
}

export function removeWaypoint(player, index) {
	const entry = stored(player);
	entry.waypoints.splice(index, 1);
	player.setDynamicProperty(WAYPOINTS, JSON.stringify(entry.waypoints));
}

export function forgetWaypoints(playerId) {
	cache.delete(playerId);
}

world.afterEvents.entityDie.subscribe((event) => {
	const player = event.deadEntity;
	try {
		const { x, y, z } = player.location;
		const death = { x: Math.floor(x), y: Math.floor(y), z: Math.floor(z), dimension: player.dimension.id };
		stored(player).death = death;
		player.setDynamicProperty(DEATH, JSON.stringify(death));
	} catch {
		// a player who left as they died has nothing to keep it on
	}
}, { entityTypes: ["minecraft:player"] });
