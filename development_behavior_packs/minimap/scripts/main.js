// Draws every player's map, and listens for the few commands the add-on has.
//
// The map is written into the action bar, which fades out on its own after a few seconds. Redrawing it
// five times a second is what keeps it on screen, and it is far below the rate at which the fade would
// start to show.

import { CommandPermissionLevel, CustomCommandStatus, system, world } from "@minecraft/server";
import { openMenu } from "./menu.js";
import { calibration, draw } from "./render.js";
import { beginPass } from "./terrain.js";
import { forget, save, settingsOf } from "./settings.js";

const REFRESH = 4;          // ticks between redraws
const CALIBRATE_FOR = 600;  // ticks the font ruler stays up when it is asked for
const QUIET = 200;          // ticks of silence after a complaint, so one broken frame is not a wall of log

const calibrating = new Map();   // player id -> the tick the ruler comes down
const drawn = new Map();         // player id -> the last map that drew, so one bad pass is not a blank screen
let complained = -QUIET;
let spent = 0;      // milliseconds the last pass took, for minimap:perf
let worst = 0;

system.runInterval(() => {
	const started = Date.now();
	const tick = system.currentTick;
	const players = world.getAllPlayers();
	let widest = 0;
	for (const player of players) {
		const settings = settingsOf(player);
		if (settings.on) widest = Math.max(widest, settings.size * settings.size);
	}
	beginPass(widest);
	for (const player of players) {
		try {
			const settings = settingsOf(player);
			if (!settings.on) continue;
			const until = calibrating.get(player.id);
			if (until !== undefined && tick > until) calibrating.delete(player.id);
			const text = until !== undefined && tick <= until ? calibration() : draw(player, settings, tick);
			drawn.set(player.id, text);
			player.onScreenDisplay.setActionBar(text);
		} catch (error) {
			// the map is a picture of a moment, so the moment before it is a better answer than a
			// screen with no map on it at all
			const last = drawn.get(player.id);
			if (last !== undefined) {
				try {
					player.onScreenDisplay.setActionBar(last);
				} catch { /* the player is on their way out of the world */ }
			}
			if (tick - complained >= QUIET) {
				complained = tick;
				console.warn(`[minimap] ${error}`);
			}
		}
	}
	spent = Date.now() - started;
	if (spent > worst) worst = spent;
}, REFRESH);

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
// and it means the map can be set up without typing a command.
world.afterEvents.itemUse.subscribe((event) => {
	if (event.itemStack.typeId !== "minecraft:compass") return;
	run(event.source, "menu", "");
});

world.afterEvents.playerLeave.subscribe((event) => {
	forget(event.playerId);
	calibrating.delete(event.playerId);
	drawn.delete(event.playerId);
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
			save(player, { [key]: Number.isNaN(number) ? value === "true" : number });
			break;
		}
		case "calibrate":
			// the ruler the font was measured with, so the cell size can be checked again from a screenshot
			calibrating.set(player.id, system.currentTick + CALIBRATE_FOR);
			break;
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
