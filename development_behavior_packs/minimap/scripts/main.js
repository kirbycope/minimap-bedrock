// Draws every player's map, and listens for the few commands the add-on has.
//
// The map is sent as a title, which the resource pack's HUD layer keeps and draws as a grid of cells
// (see tools/hud.py). The HUD holds the last map until the next, so a title is only sent when the map
// changed, and now and then besides for a HUD that was rebuilt since: a rejoin, a dimension change.

import { CommandPermissionLevel, CustomCommandStatus, system, world } from "@minecraft/server";
import { openMenu } from "./menu.js";
import { draw, hidden } from "./render.js";
import { beginPass } from "./terrain.js";
import { forget, save, settingsOf } from "./settings.js";

const REFRESH = 4;          // ticks between redraws
const RESEND = 100;         // ticks after which an unchanged map is sent again
const QUIET = 200;          // ticks of silence after a complaint, so one broken frame is not a wall of log

const sent = new Map();   // player id -> { title, tick } of the last map sent
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
			const title = settings.on ? draw(player, settings, tick) : hidden();
			const last = sent.get(player.id);
			// a hidden map is said once, so a player who turned it off gets their titles back to themselves
			if (last !== undefined && last.title === title && (!settings.on || tick - last.tick < RESEND)) continue;
			player.onScreenDisplay.setTitle(title, { fadeInDuration: 0, stayDuration: 1, fadeOutDuration: 0 });
			sent.set(player.id, { title, tick });
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
	sent.delete(event.playerId);
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
