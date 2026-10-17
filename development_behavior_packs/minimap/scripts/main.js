// Draws every player's map, and listens for the few commands the add-on has.
//
// The map is sent as a title, which the resource pack's HUD layer keeps and draws as a grid of cells
// (see tools/hud.py). The HUD holds the last map until the next, so a title is only sent when the map
// changed, and now and then besides for a HUD that was rebuilt since: a rejoin, a dimension change.

import { CommandPermissionLevel, CustomCommandStatus, system, world } from "@minecraft/server";
import { openMenu } from "./menu.js";
import { draw, hidden } from "./render.js";
import { beginPass } from "./terrain.js";
import { forget, save, settingsOf, shownWith } from "./settings.js";
import { addWaypoint, forgetWaypoints } from "./waypoints.js";
import { WAYPOINT_COLOURS } from "./palette.js";

const REFRESH = 4;          // ticks between redraws, at the most
const RESEND = 100;         // ticks after which every part of the map is sent again, for a HUD rebuilt since
const QUIET = 200;          // ticks of silence after a complaint, so one broken frame is not a wall of log

// A title is at most 512 characters, so a map is several (render.js): the header and a title per few
// rows. A player gets one title a tick, so the HUD sees every one of them, and only the parts that
// changed since they were last sent. A player's queue is refilled once it has gone out.
const players = new Map();   // player id -> { sent: [title per part], queue: [part index], drawn, resent }
let complained = -QUIET;
let spent = 0;      // milliseconds the last pass took, for minimap:perf
let worst = 0;

system.runInterval(() => {
	const started = Date.now();
	const tick = system.currentTick;
	const all = world.getAllPlayers();
	let widest = 0;
	for (const player of all) {
		const settings = shownWith(settingsOf(player));
		if (settings.on) widest = Math.max(widest, settings.size * settings.size);
	}
	let began = false;
	for (const player of all) {
		try {
			let state = players.get(player.id);
			if (state === undefined) players.set(player.id, state = { sent: [], queue: [], parts: [], drawn: -REFRESH, resent: tick });
			if (state.queue.length === 0 && tick - state.drawn >= REFRESH) {
				const settings = shownWith(settingsOf(player));
				if (settings.on && !began) { beginPass(widest); began = true; }
				state.parts = settings.on ? draw(player, settings, tick) : hidden();
				state.drawn = tick;
				const everything = tick - state.resent >= RESEND;
				if (everything) state.resent = tick;
				state.queue = state.parts.map((_, part) => part).filter((part) => everything || state.sent[part] !== state.parts[part]);
			}
			const part = state.queue.shift();
			if (part === undefined) continue;
			player.onScreenDisplay.setTitle(state.parts[part], { fadeInDuration: 0, stayDuration: 1, fadeOutDuration: 0 });
			state.sent[part] = state.parts[part];
		} catch (error) {
			// a pass that throws sends nothing, and the HUD goes on showing the map before it
			if (tick - complained >= QUIET) {
				complained = tick;
				console.warn(`[minimap] ${error}`);
			}
		}
	}
	spent = Date.now() - started;
	if (spent > worst) worst = spent;
}, 1);

system.afterEvents.scriptEventReceive.subscribe((event) => {
	const player = event.sourceEntity;
	if (player === undefined || player.typeId !== "minecraft:player") return;
	run(player, event.id.slice("minimap:".length), event.message);
}, { namespaces: ["minimap"] });

system.beforeEvents.startup.subscribe((event) => {
	try {
		event.customCommandRegistry.registerCommand({
			name: "minimap:menu",
			description: "Open the minimap settings",
			permissionLevel: CommandPermissionLevel.Any,
			cheatsRequired: false,
		}, (origin) => {
			const player = origin.sourceEntity;
			if (player === undefined || player.typeId !== "minecraft:player") {
				return { status: CustomCommandStatus.Failure, message: "Only a player has a minimap" };
			}
			system.run(() => run(player, "menu", ""));
			return { status: CustomCommandStatus.Success };
		});
	} catch (error) {
		console.warn(`[minimap] no custom command, use /scriptevent minimap:menu instead: ${error}`);
	}
});

// A compass opens the menu. It is the one item in the game that is already about finding your way,
// and it means the map can be set up without typing a command. Sneaking as you use it enlarges the map
// instead, and does it again to put it back.
world.afterEvents.itemUse.subscribe((event) => {
	if (event.itemStack.typeId !== "minecraft:compass") return;
	if (event.source.isSneaking) run(event.source, "enlarge", "");
	else run(event.source, "menu", "");
});

world.afterEvents.playerLeave.subscribe((event) => {
	forget(event.playerId);
	forgetWaypoints(event.playerId);
	players.delete(event.playerId);
});

function run(player, command, message) {
	switch (command) {
		case "menu":
			system.run(() => openMenu(player).catch((error) => console.warn(`[minimap] ${error}`)));
			break;
		case "on":
		case "off":
			save(player, { on: command === "on" });
			break;
		case "enlarge":
			save(player, { enlarged: !settingsOf(player).enlarged });
			break;
		case "toggle":
			save(player, { on: !settingsOf(player).on });
			break;
		case "set": {
			// /scriptevent minimap:set size 13, for a player who would rather type than use the form
			const [key, value] = message.trim().split(/\s+/);
			if (!(key in settingsOf(player))) {
				player.sendMessage(`[minimap] no setting called "${key}"`);
				break;
			}
			const number = Number(value);
			// a word that is not true or false is a setting's name for itself, as in shape circle
			const word = value === "true" || value === "false" ? value === "true" : value;
			save(player, { [key]: Number.isNaN(number) ? word : number });
			break;
		}
		case "waypoint": {
			// /scriptevent minimap:waypoint [colour] [name], a waypoint where you stand
			const words = message.trim().split(/\s+/).filter(Boolean);
			const colour = words[0] in WAYPOINT_COLOURS ? words.shift() : "white";
			if (!addWaypoint(player, words.join(" "), colour)) player.sendMessage("[minimap] the waypoint list is full");
			break;
		}
		case "perf": {
			// the log as well as the chat, because this is for whoever is working on the add-on
			const report = `[minimap] last pass ${spent} ms, worst ${worst} ms, ${world.getAllPlayers().length} player(s)`;
			player.sendMessage(report);
			console.warn(report);
			worst = 0;
			break;
		}
		default:
			player.sendMessage(`[minimap] unknown command "${command}${message ? ` ${message}` : ""}"`);
	}
}
