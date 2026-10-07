"""FNS HA Tweaks — shared parts for multiple Home Assistant instances.

The integration is installed via HACS, so every new version is offered as an
update like any other repository. On startup it unpacks what it ships with
and sets up what is needed:

- the ``fns_mushroom`` theme into ``themes/fns-mushroom/fns-mushroom.yaml``
  and reloads themes
- shared UIX foundries into ``uix/fns_shared.yaml`` and registers them in UIX

The sun line card is deployed into the header of the default dashboard by the
``fns_shared.deploy_sun_card`` service (the dashboard is not a file, so it is
not deployed automatically).

A single ``fns_shared:`` line in ``configuration.yaml`` is enough.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from typing import Any

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, Event, HomeAssistant, ServiceCall
from homeassistant.helpers.typing import ConfigType

DOMAIN = "fns_shared"
UIX_DOMAIN = "uix"
UIX_CONF_FOUNDRY_FILES = "foundry_files"

THEME_SOURCE = "theme/fns-mushroom.yaml"
THEME_TARGET = "themes/fns-mushroom/fns-mushroom.yaml"
FOUNDRIES_SOURCE = "foundries/fns_shared.yaml"
FOUNDRIES_TARGET = "uix/fns_shared.yaml"
SUN_CARD_SOURCE = "cards/sun_line.json"
SUN_CARD_MARKER = "Slunce a měsíc"  # card title used to find it in live dashboards; do not change

SERVICE_DEPLOY_SUN_CARD = "deploy_sun_card"

# Frontend modules: (file in the integration, URL it is served under)
FRONTEND_MODULES = (
    ("www/fns_forge_editor.js", "/fns_shared/fns_forge_editor.js"),
    ("www/fns_sun_line.js", "/fns_shared/fns_sun_line.js"),
)

_LOGGER = logging.getLogger(__name__)


def _deploy_file(hass: HomeAssistant, source: str, target: str) -> bool:
    """Copy a file from the integration into the config. Returns True if it changed."""
    src = os.path.join(os.path.dirname(__file__), source)
    dst = hass.config.path(target)
    if os.path.exists(dst):
        with open(src, "rb") as fh_src, open(dst, "rb") as fh_dst:
            if fh_src.read() == fh_dst.read():
                return False
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(src, dst)
    _LOGGER.info("%s: updated %s", DOMAIN, target)
    return True


def _uix_entry(hass: HomeAssistant) -> ConfigEntry | None:
    entries = hass.config_entries.async_entries(UIX_DOMAIN)
    return entries[0] if entries else None


def _load_sun_card() -> dict[str, Any]:
    with open(os.path.join(os.path.dirname(__file__), SUN_CARD_SOURCE), encoding="utf-8") as fh:
        return json.load(fh)


# Lunar Phase entities carry the location name in their id, so the card templates look them up with a
# regex over `states.sensor`. Such a template, however, listens to the whole sensor domain and HA
# re-renders it on every change of any sensor (several times a second for a 12 kB style on the default
# dashboard). So the entities are hard-coded when the card is deployed; the lookup stays only as a
# fallback when the Lunar Phase integration is not present on the instance.
SUN_CARD_LOOKUPS = {
    "e_mr": "_moon_rise",
    "e_ms": "_moon_set",
    "e_il": "_moon_illumination_fraction",
}


def _resolve_sun_card_entities(hass: HomeAssistant, card: dict[str, Any]) -> dict[str, Any]:
    text = json.dumps(card, ensure_ascii=False)
    for var, suffix in SUN_CARD_LOOKUPS.items():
        entity_id = next(
            (state.entity_id for state in hass.states.async_all("sensor")
             if state.entity_id.endswith(suffix)),
            None,
        )
        if entity_id is None:
            continue
        lookup = (
            f"{{% set {var} = states.sensor | selectattr('entity_id', 'search', '{suffix}$')"
            " | map(attribute='entity_id') | first | default('', true) %}"
        )
        text = text.replace(json.dumps(lookup, ensure_ascii=False)[1:-1], f"{{% set {var} = '{entity_id}' %}}")
    return json.loads(text)


async def _load_default_dashboard(hass: HomeAssistant):
    """Return (store, config) of the default dashboard across HA versions."""
    lovelace = hass.data.get("lovelace")
    dashboards = getattr(lovelace, "dashboards", None)
    if dashboards is None and isinstance(lovelace, dict):
        dashboards = lovelace.get("dashboards")
    if not dashboards:
        raise ValueError("lovelace is not available")

    # Depending on the HA version the default dashboard is under the key "lovelace" or None;
    # the latter is usually auto-generated and has no stored config.
    for key in ("lovelace", None):
        store = dashboards.get(key)
        if store is None:
            continue
        try:
            return store, await store.async_load(False)
        except Exception:  # ConfigNotFound and friends — try the next key
            continue
    raise ValueError("the default dashboard has no stored config (not in storage mode)")


def _find_sun_card(config: dict[str, Any]) -> dict[str, Any] | None:
    """Find the sun line card in the dashboard, or return None."""
    stack: list[Any] = [config]
    while stack:
        node = stack.pop()
        if isinstance(node, list):
            for item in node:
                if (isinstance(item, dict)
                        and str(item.get("type", "")).startswith("custom:mushroom-template")
                        and SUN_CARD_MARKER in json.dumps(item, ensure_ascii=False)):
                    return item
                stack.append(item)
        elif isinstance(node, dict):
            stack.extend(node.values())
    return None


def _replace_sun_card(config: dict[str, Any], card: dict[str, Any]) -> str:
    """Replace the sun card, or insert it into the header of the first view."""
    stack: list[Any] = [config]
    while stack:
        node = stack.pop()
        if isinstance(node, list):
            for i, item in enumerate(node):
                if (isinstance(item, dict)
                        and str(item.get("type", "")).startswith("custom:mushroom-template")
                        and SUN_CARD_MARKER in json.dumps(item, ensure_ascii=False)):
                    node[i] = card
                    return "replaced"
                stack.append(item)
        elif isinstance(node, dict):
            stack.extend(node.values())

    views = config.get("views") or []
    if not views:
        raise ValueError("the default dashboard has no views")
    header_cards = views[0].get("header", {}).get("card", {}).get("cards")
    if isinstance(header_cards, list):
        header_cards.append(card)
        return "added to the header"
    views[0].setdefault("cards", []).append(card)
    return "added to the end of the first view"


def _read_manifest_version(base: str) -> str:
    """Read the version from the integration manifest (runs in the executor, not the event loop)."""
    try:
        with open(os.path.join(base, "manifest.json"), encoding="utf-8") as fh:
            return json.load(fh).get("version", "0")
    except OSError:
        return "0"


async def _register_frontend(hass: HomeAssistant) -> None:
    """Serve the integration's frontend modules and load them in the browser."""
    base = os.path.dirname(__file__)
    version = await hass.async_add_executor_job(_read_manifest_version, base)
    for soubor, adresa in FRONTEND_MODULES:
        try:
            await hass.http.async_register_static_paths(
                [StaticPathConfig(adresa, os.path.join(base, soubor), True)]
            )
        except Exception as err:  # older HA or repeated registration
            _LOGGER.debug("%s: static path %s: %s", DOMAIN, adresa, err)
        # the version in the query busts the browser cache once the integration is updated
        add_extra_js_url(hass, f"{adresa}?v={version}")


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Deploy the shared files and register the sun card service."""

    async def _apply(_event: Event | None = None) -> None:
        theme_changed = await hass.async_add_executor_job(
            _deploy_file, hass, THEME_SOURCE, THEME_TARGET
        )
        foundries_changed = await hass.async_add_executor_job(
            _deploy_file, hass, FOUNDRIES_SOURCE, FOUNDRIES_TARGET
        )

        if theme_changed:
            await hass.services.async_call("frontend", "reload_themes", blocking=True)

        entry = _uix_entry(hass)
        if entry is None:
            _LOGGER.warning("%s: uix integration not found, foundries not registered", DOMAIN)
            return

        files = list(entry.options.get(UIX_CONF_FOUNDRY_FILES, []))
        if FOUNDRIES_TARGET not in files:
            files.append(FOUNDRIES_TARGET)
            hass.config_entries.async_update_entry(
                entry, options={**entry.options, UIX_CONF_FOUNDRY_FILES: files}
            )
            _LOGGER.info("%s: %s registered in UIX", DOMAIN, FOUNDRIES_TARGET)
        elif foundries_changed:
            await hass.config_entries.async_reload(entry.entry_id)

        try:
            _LOGGER.info("%s: sun card — %s", DOMAIN, await _sync_sun_card(only_if_present=True))
        except Exception as err:  # the dashboard may not be in storage mode
            _LOGGER.warning("%s: cannot update the sun card (%s)", DOMAIN, err)

    async def _sync_sun_card(only_if_present: bool = False) -> str:
        store, dashboard = await _load_default_dashboard(hass)
        card = _resolve_sun_card_entities(hass, await hass.async_add_executor_job(_load_sun_card))
        if only_if_present:
            # On startup the card is not forced anywhere — only the one already in the dashboard
            # is updated, and only if it differs, so the dashboard is not rewritten needlessly.
            current = _find_sun_card(dashboard)
            if current is None:
                return "not in the dashboard"
            if current == card:
                return "unchanged"
        where = _replace_sun_card(dashboard, card)
        await store.async_save(dashboard)
        return where

    async def _deploy_sun_card(_call: ServiceCall) -> None:
        _LOGGER.info("%s: sun card %s", DOMAIN, await _sync_sun_card())

    hass.services.async_register(DOMAIN, SERVICE_DEPLOY_SUN_CARD, _deploy_sun_card)
    await _register_frontend(hass)

    if hass.state is CoreState.running:  # integration reloaded while running
        await _apply()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _apply)
    return True
