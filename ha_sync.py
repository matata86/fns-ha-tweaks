#!/usr/bin/env python3
"""Synchronizace sdílených částí Home Assistantu mezi instancemi HA Home a HA Office.

Sdílí se:
  - téma fns-mushroom (včetně cirkadiánního podbarvení a vrstev počasí)
  - UIX foundries level_tile / mini_graph / threshold_tile
  - karta sluneční linky v hlavičce Přehledu

Použití:
    python3 ha_sync.py status [home|office|all]
    python3 ha_sync.py pull   home|office        # živý stav -> repozitář
    python3 ha_sync.py push   home|office|all    # repozitář -> živá instance
    python3 ha_sync.py diff   home|office        # rozdíl repozitář vs. živý stav

Přístupy se čtou z ~/.config/ha-sync.json (viz secrets.example.json), nikdy z repozitáře.
"""
import argparse
import asyncio
import difflib
import json
import os
import sys

import paramiko
import websockets
import yaml

REPO = os.path.dirname(os.path.abspath(__file__))
SECRETS = os.path.expanduser("~/.config/ha-sync.json")
SHARED_FOUNDRIES = os.path.join(REPO, "shared/uix/foundries.shared.yaml")
SHARED_THEME = os.path.join(REPO, "shared/theme/fns-mushroom.yaml")
SUN_CARD = os.path.join(REPO, "shared/cards/sun_line.json")
SUN_MARKER = "Slunce a měsíc"


def load_config():
    if not os.path.exists(SECRETS):
        sys.exit(f"Chybí {SECRETS} — vytvoř podle secrets.example.json")
    with open(SECRETS) as fh:
        return json.load(fh)


def instance(cfg, name):
    if name not in cfg["instances"]:
        sys.exit(f"Neznámá instance {name}")
    inst = dict(cfg["instances"][name])
    inst["name"] = name
    inst["local_foundries"] = os.path.join(REPO, "instances", name, "foundries.local.yaml")
    return inst


# ---------------------------------------------------------------- SSH


def ssh(inst):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(inst["ssh_host"], port=inst.get("ssh_port", 22),
                   username=inst.get("ssh_user", "root"), password=inst["ssh_password"],
                   look_for_keys=False, allow_agent=False, timeout=30)
    return client


def read_remote(inst, path):
    client = ssh(inst)
    try:
        with client.open_sftp() as sftp, sftp.open(path) as fh:
            return fh.read().decode()
    finally:
        client.close()


def write_remote(inst, path, data):
    client = ssh(inst)
    try:
        with client.open_sftp() as sftp:
            with sftp.open(path, "w") as fh:
                fh.write(data)
    finally:
        client.close()


# ---------------------------------------------------------------- websocket


async def ws_calls(inst, messages):
    url = f"ws://{inst['host']}:{inst.get('port', 8123)}/api/websocket"
    out = []
    async with websockets.connect(url, max_size=80_000_000) as sock:
        await sock.recv()
        await sock.send(json.dumps({"type": "auth", "access_token": inst["token"]}))
        auth = json.loads(await sock.recv())
        if auth.get("type") != "auth_ok":
            sys.exit(f"{inst['name']}: autentizace selhala")
        for i, msg in enumerate(messages, start=2):
            msg = dict(msg, id=i)
            await sock.send(json.dumps(msg))
            while True:
                res = json.loads(await sock.recv())
                if res.get("id") == i:
                    out.append(res)
                    break
    return out


def ws(inst, messages):
    return asyncio.run(ws_calls(inst, messages))


# ---------------------------------------------------------------- foundries


def merged_foundries(inst):
    shared = yaml.safe_load(open(SHARED_FOUNDRIES))["uix_foundries"]
    local = {}
    if os.path.exists(inst["local_foundries"]):
        local = yaml.safe_load(open(inst["local_foundries"])).get("uix_foundries") or {}
    merged = dict(local)
    merged.update(shared)
    header = ("# Generováno ha_sync.py — needituj na instanci.\n"
              "# Sdílené: shared/uix/foundries.shared.yaml\n"
              f"# Lokální: instances/{inst['name']}/foundries.local.yaml\n")
    return header + yaml.safe_dump({"uix_foundries": merged}, allow_unicode=True,
                                   sort_keys=True, width=1000)


def split_foundries(inst, text):
    """Živý soubor rozdělí zpět na sdílenou a lokální část."""
    live = yaml.safe_load(text)["uix_foundries"]
    shared_keys = set(yaml.safe_load(open(SHARED_FOUNDRIES))["uix_foundries"])
    shared = {k: v for k, v in live.items() if k in shared_keys}
    local = {k: v for k, v in live.items() if k not in shared_keys}
    return shared, local


# ---------------------------------------------------------------- sluneční karta


def find_sun_card(config):
    """Vrátí (rodičovský seznam, index) karty sluneční linky, nebo (None, None)."""
    found = []

    def walk(node):
        if isinstance(node, list):
            for i, item in enumerate(node):
                if (isinstance(item, dict)
                        and str(item.get("type", "")).startswith("custom:mushroom-template")
                        and SUN_MARKER in json.dumps(item, ensure_ascii=False)):
                    found.append((node, i))
                walk(item)
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)

    walk(config)
    return found[0] if found else (None, None)


# ---------------------------------------------------------------- akce


def do_pull(inst):
    theme = read_remote(inst, inst["theme_path"])
    open(SHARED_THEME, "w").write(theme)
    shared, local = split_foundries(inst, read_remote(inst, inst["foundries_path"]))
    yaml.safe_dump({"uix_foundries": shared}, open(SHARED_FOUNDRIES, "w"),
                   allow_unicode=True, sort_keys=True, width=1000)
    yaml.safe_dump({"uix_foundries": local}, open(inst["local_foundries"], "w"),
                   allow_unicode=True, sort_keys=True, width=1000)
    config = ws(inst, [{"type": "lovelace/config", "url_path": inst.get("dashboard")}])[0]["result"]
    parent, idx = find_sun_card(config)
    if parent is not None:
        json.dump(parent[idx], open(SUN_CARD, "w"), ensure_ascii=False, indent=1)
    print(f"{inst['name']}: staženo téma, foundries"
          + (", karta slunce" if parent is not None else ", karta slunce NENALEZENA"))


def do_push(inst):
    write_remote(inst, inst["theme_path"], open(SHARED_THEME).read())
    write_remote(inst, inst["foundries_path"], merged_foundries(inst))
    config = ws(inst, [{"type": "lovelace/config", "url_path": inst.get("dashboard")}])[0]["result"]
    parent, idx = find_sun_card(config)
    card_msg = "karta slunce nenalezena (přeskočeno)"
    if parent is not None:
        parent[idx] = json.load(open(SUN_CARD))
        res = ws(inst, [{"type": "lovelace/config/save",
                         "url_path": inst.get("dashboard"), "config": config}])[0]
        card_msg = "karta slunce uložena" if res.get("success") else f"karta slunce CHYBA {res}"
    reloads = ws(inst, [
        {"type": "uix/reload_foundry_files"},
        {"type": "call_service", "domain": "frontend", "service": "reload_themes", "service_data": {}},
    ])
    ok = all(r.get("success") for r in reloads)
    print(f"{inst['name']}: nahráno téma + foundries, {card_msg}, reload {'OK' if ok else reloads}")


def do_status(inst):
    rows = []
    live_theme = read_remote(inst, inst["theme_path"])
    rows.append(("téma", live_theme == open(SHARED_THEME).read()))
    live_foundries = read_remote(inst, inst["foundries_path"])
    rows.append(("foundries", yaml.safe_load(live_foundries) == yaml.safe_load(merged_foundries(inst))))
    config = ws(inst, [{"type": "lovelace/config", "url_path": inst.get("dashboard")}])[0]["result"]
    parent, idx = find_sun_card(config)
    same = parent is not None and parent[idx] == json.load(open(SUN_CARD))
    rows.append(("karta slunce", same))
    for label, ok in rows:
        print(f"{inst['name']:7} {label:14} {'shodné' if ok else 'LIŠÍ SE'}")


def do_diff(inst):
    live_theme = read_remote(inst, inst["theme_path"]).splitlines()
    repo_theme = open(SHARED_THEME).read().splitlines()
    print("\n".join(difflib.unified_diff(repo_theme, live_theme, "repo/téma",
                                         f"{inst['name']}/téma", lineterm="")) or "téma: shodné")
    live_f = yaml.safe_dump(yaml.safe_load(read_remote(inst, inst["foundries_path"])),
                            allow_unicode=True, sort_keys=True, width=1000).splitlines()
    repo_f = yaml.safe_dump(yaml.safe_load(merged_foundries(inst)),
                            allow_unicode=True, sort_keys=True, width=1000).splitlines()
    print("\n".join(difflib.unified_diff(repo_f, live_f, "repo/foundries",
                                         f"{inst['name']}/foundries", lineterm="")) or "foundries: shodné")


ACTIONS = {"pull": do_pull, "push": do_push, "status": do_status, "diff": do_diff}


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=sorted(ACTIONS))
    parser.add_argument("target", nargs="?", default="all")
    args = parser.parse_args()
    cfg = load_config()
    targets = list(cfg["instances"]) if args.target == "all" else [args.target]
    if args.action == "pull" and len(targets) > 1:
        sys.exit("pull vyžaduje konkrétní instanci")
    for name in targets:
        ACTIONS[args.action](instance(cfg, name))


if __name__ == "__main__":
    main()
