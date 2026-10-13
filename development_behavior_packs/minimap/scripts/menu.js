// The menu, which is the whole of the add-on's interface.
//
// Every setting is a button rather than a form field, because the useful ones are pressed over and
// over: zoom in twice, nudge the map up three times. Each press saves, closes and opens the menu
// again, so the next press is one tap away and the labels always show where the settings now stand.

import { ActionFormData } from "@minecraft/server-ui";
import { SIZES, ZOOMS, fits, nudge, save, settingsOf, step } from "./settings.js";

const CLOSE = -1;

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
		["Move up", () => nudge(player, "up", 1)],
		["Move down", () => nudge(player, "up", -1)],
		["Move left", () => nudge(player, "right", -1)],
		["Move right", () => nudge(player, "right", 1)],
		[`Turn with me: ${settings.rotate ? "on" : "off"}`, () => save(player, { rotate: !settings.rotate })],
		[`Mobs and players: ${settings.entities ? "on" : "off"}`, () => save(player, { entities: !settings.entities })],
		[`Coordinates: ${settings.coords ? "on" : "off"}`, () => save(player, { coords: !settings.coords })],
		["Hide the map", () => { save(player, { on: false }); return CLOSE; }],
	];

	const form = new ActionFormData().title("Minimap").body("The map is drawn where the action bar goes. Minecraft decides that spot, so the move buttons are how you put the map in the corner you want.");
	for (const [label] of buttons) form.button(label);
	return form.show(player).then((response) => {
		if (response.canceled || response.selection === undefined) return;
		if (buttons[response.selection][1]() === CLOSE) return;
		return openMenu(player);
	});
}
