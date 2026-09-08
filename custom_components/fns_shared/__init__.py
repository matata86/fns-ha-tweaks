"""FNS HA Tweaks — sdílené části více instancí Home Assistantu.

Integrace se instaluje přes HACS, takže se každá nová verze nabídne k
aktualizaci jako u kteréhokoli jiného repozitáře. Sama při startu rozbalí to,
co s sebou nese, a nastaví, co je potřeba:

- motiv ``fns_mushroom`` do ``themes/fns-mushroom/fns-mushroom.yaml``
  a načte témata
- sdílené UIX foundries do ``uix/fns_shared.yaml`` a zaregistruje je v UIX

Kartu sluneční linky nasadí do hlavičky výchozího dashboardu služba
``fns_shared.deploy_sun_card`` (dashboard není soubor, proto se nenasazuje sám).

Do ``configuration.yaml`` stačí řádek ``fns_shared:``.
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
SUN_CARD_MARKER = "Slunce a měsíc"

SERVICE_DEPLOY_SUN_CARD = "deploy_sun_card"

# Frontendové moduly: (soubor v integraci, adresa, pod kterou se servírují)
FRONTEND_MODULES = (
    ("www/fns_forge_editor.js", "/fns_shared/fns_forge_editor.js"),
    ("www/fns_sun_line.js", "/fns_shared/fns_sun_line.js"),
)

_LOGGER = logging.getLogger(__name__)


def _deploy_file(hass: HomeAssistant, source: str, target: str) -> bool:
    """Zkopíruje soubor z integrace do konfigurace. Vrací True při změně."""
    src = os.path.join(os.path.dirname(__file__), source)
    dst = hass.config.path(target)
    if os.path.exists(dst):
        with open(src, "rb") as fh_src, open(dst, "rb") as fh_dst:
            if fh_src.read() == fh_dst.read():
                return False
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(src, dst)
    _LOGGER.info("%s: aktualizováno %s", DOMAIN, target)
    return True


def _uix_entry(hass: HomeAssistant) -> ConfigEntry | None:
    entries = hass.config_entries.async_entries(UIX_DOMAIN)
    return entries[0] if entries else None


def _load_sun_card() -> dict[str, Any]:
    with open(os.path.join(os.path.dirname(__file__), SUN_CARD_SOURCE), encoding="utf-8") as fh:
        return json.load(fh)


async def _load_default_dashboard(hass: HomeAssistant):
    """Vrátí (úložiště, konfigurace) výchozího dashboardu napříč verzemi HA."""
    lovelace = hass.data.get("lovelace")
    dashboards = getattr(lovelace, "dashboards", None)
    if dashboards is None and isinstance(lovelace, dict):
        dashboards = lovelace.get("dashboards")
    if not dashboards:
        raise ValueError("lovelace není k dispozici")

    # Podle verze HA je výchozí dashboard pod klíčem "lovelace" nebo None;
    # ten druhý bývá automaticky generovaný a uloženou konfiguraci nemá.
    for key in ("lovelace", None):
        store = dashboards.get(key)
        if store is None:
            continue
        try:
            return store, await store.async_load(False)
        except Exception:  # ConfigNotFound a spol. — zkusíme další klíč
            continue
    raise ValueError("výchozí dashboard nemá uloženou konfiguraci (není ve storage režimu)")


def _find_sun_card(config: dict[str, Any]) -> dict[str, Any] | None:
    """Najde kartu sluneční linky v dashboardu, nebo vrátí None."""
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
    """Nahradí kartu slunce, nebo ji vloží do hlavičky prvního pohledu."""
    stack: list[Any] = [config]
    while stack:
        node = stack.pop()
        if isinstance(node, list):
            for i, item in enumerate(node):
                if (isinstance(item, dict)
                        and str(item.get("type", "")).startswith("custom:mushroom-template")
                        and SUN_CARD_MARKER in json.dumps(item, ensure_ascii=False)):
                    node[i] = card
                    return "nahrazena"
                stack.append(item)
        elif isinstance(node, dict):
            stack.extend(node.values())

    views = config.get("views") or []
    if not views:
        raise ValueError("výchozí dashboard nemá žádný pohled")
    header_cards = views[0].get("header", {}).get("card", {}).get("cards")
    if isinstance(header_cards, list):
        header_cards.append(card)
        return "přidána do hlavičky"
    views[0].setdefault("cards", []).append(card)
    return "přidána na konec prvního pohledu"


async def _register_frontend(hass: HomeAssistant) -> None:
    """Naservíruje frontendové moduly integrace a načte je v prohlížeči."""
    base = os.path.dirname(__file__)
    version = "0"
    try:
        with open(os.path.join(base, "manifest.json"), encoding="utf-8") as fh:
            version = json.load(fh).get("version", "0")
    except OSError:
        pass
    for soubor, adresa in FRONTEND_MODULES:
        try:
            await hass.http.async_register_static_paths(
                [StaticPathConfig(adresa, os.path.join(base, soubor), True)]
            )
        except Exception as err:  # starší HA nebo opakovaná registrace
            _LOGGER.debug("%s: statická cesta %s: %s", DOMAIN, adresa, err)
        # verze v dotazu shodí cache prohlížeče, jakmile se integrace aktualizuje
        add_extra_js_url(hass, f"{adresa}?v={version}")


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Nasadí sdílené soubory a zaregistruje službu pro kartu slunce."""

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
            _LOGGER.warning("%s: integrace uix nenalezena, foundries nezaregistrovány", DOMAIN)
            return

        files = list(entry.options.get(UIX_CONF_FOUNDRY_FILES, []))
        if FOUNDRIES_TARGET not in files:
            files.append(FOUNDRIES_TARGET)
            hass.config_entries.async_update_entry(
                entry, options={**entry.options, UIX_CONF_FOUNDRY_FILES: files}
            )
            _LOGGER.info("%s: %s zaregistrován v UIX", DOMAIN, FOUNDRIES_TARGET)
        elif foundries_changed:
            await hass.config_entries.async_reload(entry.entry_id)

        try:
            _LOGGER.info("%s: karta slunce — %s", DOMAIN, await _sync_sun_card(only_if_present=True))
        except Exception as err:  # dashboard nemusí být ve storage režimu
            _LOGGER.warning("%s: kartu slunce nelze aktualizovat (%s)", DOMAIN, err)

    async def _sync_sun_card(only_if_present: bool = False) -> str:
        store, dashboard = await _load_default_dashboard(hass)
        card = await hass.async_add_executor_job(_load_sun_card)
        if only_if_present:
            # Při startu kartu nikam nevnucujeme — jen aktualizujeme tu, která už v dashboardu je,
            # a to jen když se liší, ať se dashboard zbytečně nepřepisuje.
            current = _find_sun_card(dashboard)
            if current is None:
                return "v dashboardu není"
            if current == card:
                return "beze změny"
        where = _replace_sun_card(dashboard, card)
        await store.async_save(dashboard)
        return where

    async def _deploy_sun_card(_call: ServiceCall) -> None:
        _LOGGER.info("%s: karta slunce %s", DOMAIN, await _sync_sun_card())

    hass.services.async_register(DOMAIN, SERVICE_DEPLOY_SUN_CARD, _deploy_sun_card)
    await _register_frontend(hass)

    if hass.state is CoreState.running:  # reload integrace za chodu
        await _apply()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _apply)
    return True
