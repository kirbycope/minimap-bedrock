"""Talk to the world through the minecraft-bedrock MCP bridge over HTTP, no client needed.

    python tools/bridge.py "time set day" "structure load skyblock:starting_islands_desert 5 61 5"
    python tools/bridge.py tool:mc_player_list                      call a bridge tool
    python tools/bridge.py tool:mc_block_get {"location":{"x":6,"y":63,"z":6}}

The bridge is the minecraft-bedrock-mcp-server on this PC; its token is read from that repository's .env.
This file comes from cobblemon-bedrock; `stage`, which built test pillars for a Pokemon, is dropped, and the
test spot is this world's spawn.
"""
import json
import os
import re
import sys
import urllib.request

URL = "http://127.0.0.1:8765/mcp"   # not localhost: Windows tries IPv6 first and the bridge listens on IPv4 only, a 2 s stall per call
ENV = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "minecraft-bedrock-mcp-server", ".env")
SPAWN = (6, 64, 6)           # where the add-on puts the player, on the starting island
PLAYER = "Kirbycope"


def token():
    for line in open(ENV, encoding="utf-8"):
        match = re.match(r"\s*BRIDGE_CLIENT_TOKEN\s*=\s*\"?([^\"\s]+)", line)
        if match: return match.group(1)
    sys.exit(f"no BRIDGE_CLIENT_TOKEN in {ENV}")


class Bridge:
    def __init__(self):
        self.headers = {"Authorization": f"Bearer {token()}", "Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        self.session = None; self.counter = 1
        self.post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "bridge.py", "version": "1"}}})
        self.post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def post(self, body):
        headers = dict(self.headers)
        if self.session: headers["mcp-session-id"] = self.session
        request = urllib.request.Request(URL, data=json.dumps(body).encode(), headers=headers)
        with urllib.request.urlopen(request, timeout=15) as response:   # a stuck bridge fails fast instead of stalling a run
            self.session = response.headers.get("mcp-session-id") or self.session
            text = response.read().decode()
        return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]

    def tool(self, tool_name, **arguments):
        self.counter += 1
        data = self.post({"jsonrpc": "2.0", "id": self.counter, "method": "tools/call", "params": {"name": tool_name, "arguments": arguments}})
        result = data[-1].get("result", data[-1])
        return "\n".join(c.get("text", "") for c in result.get("content", [])) or json.dumps(result)

    def command(self, text):
        return self.tool("mc_run_command", command=text)

    def near(self, selector, player=PLAYER):
        """How many entities match a selector around the player. A bare testfor from the bridge runs at the
        world origin, so a radius there measures distance from 0,0,0, not from anyone."""
        result = self.command(f"execute as {player} at @s run testfor @e[{selector}]")
        return int(result.split("success_count:")[1]) if "success_count:" in result else 0


def check(bridge, player=PLAYER):
    """The player is on the server and alive; raise otherwise so a batch stops at the first deviation."""
    players = bridge.tool("mc_player_list")
    if player not in players: raise RuntimeError(f"{player} is not on the server")
    if "success_count: 1" not in bridge.command(f"testfor @e[type=player,name={player}]"): raise RuntimeError(f"{player} is dead")
    return True


def protect(bridge, player=PLAYER):
    """Effects that keep a test player alive: no damage, no fall damage, drowning healed."""
    for effect in ("resistance 99999 255 true", "slow_falling 99999 1 true", "regeneration 99999 5 true", "water_breathing 99999 1 true"):
        bridge.command(f"effect {player} {effect}")


if __name__ == "__main__":
    bridge = Bridge()
    for arg in sys.argv[1:]:
        if arg.startswith("tool:"):
            name, _, raw = arg[5:].partition(" ")
            print(arg, "->", bridge.tool(name, **json.loads(raw or "{}")))
        else:
            print(arg, "->", bridge.command(arg))
