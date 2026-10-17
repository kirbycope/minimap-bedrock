// The menu, which is the whole of the add-on's interface.
//
// Every setting is a button rather than a form field, because the useful ones are pressed over and
// over: zoom in twice, grow the map twice. Each press saves, closes and opens the menu
// again, so the next press is one tap away and the labels always show where the settings now stand.

import { ActionFormData, ModalFormData } from "@minecraft/server-ui";
import { WAYPOINT_COLOURS } from "./palette.js";
import { MAX_WAYPOINTS, addWaypoint, deathOf, removeWaypoint, waypointsOf } from "./waypoints.js";
import { SIZES } from "./hud_layout.js";
import { ZOOMS, fits, save, settingsOf, step } from "./settings.js";

const CLOSE = -1;
// the lines under the map, in settings.js's LINES order
const LABELS = { coords: "Coordinates", angle: "Facing", biome: "Biome", light: "Light level", time: "Time of day" };

/** Says when a button has nothing left to give, so a press that does nothing is not a mystery. */
function capped(settings, key) {
	const list = key === "size" ? SIZES : ZOOMS;
	const at = list.indexOf(settings[key]);
	if (at === list.length - 1) return " - the largest";
	const next = list[at + 1];
	const size = key === "size" ? next : settings.size;
	const zoom = key === "zoom" ? next : settings.zoom;
	return fits(size, zoom) ? "" : " - as far as the chunks go";
}

/** Opens the menu, does what the pressed button says, and opens it again. */
export function openMenu(player) {
	const settings = settingsOf(player);
	const buttons = [
		[`Zoom in${settings.zoom === ZOOMS[0] ? " (at the closest)" : ""}`, () => step(player, "zoom", -1)],
		[`Zoom out (${settings.zoom} block${settings.zoom === 1 ? "" : "s"} a cell)${capped(settings, "zoom")}`,
			() => step(player, "zoom", 1)],
		[`Bigger (${settings.size} x ${settings.size})${capped(settings, "size")}`, () => step(player, "size", 1)],
		["Smaller", () => step(player, "size", -1)],
		[`Shape: ${settings.shape}`, () => save(player, { shape: settings.shape === "square" ? "circle" : "square" })],
		[`Turn with me: ${settings.rotate ? "on" : "off"}`, () => save(player, { rotate: !settings.rotate })],
		[`Mobs and players: ${settings.entities ? "on" : "off"}`, () => save(player, { entities: !settings.entities })],
		[`Chunk grid: ${settings.grid ? "on" : "off"}`, () => save(player, { grid: !settings.grid })],
		[`Slime chunks: ${settings.slime ? "on" : "off"}`, () => save(player, { slime: !settings.slime })],
		[`Waypoints (${waypointsOf(player).length})`, () => { waypointMenu(player); return CLOSE; }],
		...Object.entries(LABELS).map(([key, label]) =>
			[`${label}: ${settings[key] ? "on" : "off"}`, () => save(player, { [key]: !settings[key] })]),
		["Hide the map", () => { save(player, { on: false }); return CLOSE; }],
	];

	const form = new ActionFormData().title("Minimap");
	for (const [label] of buttons) form.button(label);
	return form.show(player).then((response) => {
		if (response.canceled || response.selection === undefined) return;
		if (buttons[response.selection][1]() === CLOSE) return;
		return openMenu(player);
	});
}

const COLOUR_NAMES = Object.keys(WAYPOINT_COLOURS);

/** Xaero's waypoint list: add one where you stand, show or hide them and the deathpoint, delete one. */
function waypointMenu(player) {
	const settings = settingsOf(player);
	const points = waypointsOf(player);
	const death = deathOf(player);
	const buttons = [
		[points.length < MAX_WAYPOINTS ? "Add one here" : `Add one here (the list is full at ${MAX_WAYPOINTS})`,
			() => (points.length < MAX_WAYPOINTS ? addMenu(player) : undefined)],
		[`Show waypoints: ${settings.waypoints ? "on" : "off"}`, () => save(player, { waypoints: !settings.waypoints })],
		[`Show where I died: ${settings.deathpoint ? "on" : "off"}${death ? ` (${death.x}, ${death.y}, ${death.z})` : ""}`,
			() => save(player, { deathpoint: !settings.deathpoint })],
		...points.map((point, index) => [`Delete ${point.name} (${point.colour}, ${point.x}, ${point.y}, ${point.z})`,
			() => removeWaypoint(player, index)]),
		["Back", () => CLOSE],
	];
	const form = new ActionFormData().title("Waypoints");
	for (const [label] of buttons) form.button(label);
	return form.show(player).then(async (response) => {
		if (response.canceled || response.selection === undefined) return;
		if ((await buttons[response.selection][1]()) === CLOSE) return openMenu(player);
		return waypointMenu(player);
	});
}

function addMenu(player) {
	const form = new ModalFormData()
		.title("New waypoint")
		.textField("Name", `Waypoint ${waypointsOf(player).length + 1}`)
		.dropdown("Colour", COLOUR_NAMES.map((name) => name.charAt(0).toUpperCase() + name.slice(1)));
	return form.show(player).then((response) => {
		if (response.canceled || response.formValues === undefined) return;
		const [name, colour] = response.formValues;
		addWaypoint(player, String(name ?? ""), COLOUR_NAMES[Number(colour) || 0]);
	});
}
