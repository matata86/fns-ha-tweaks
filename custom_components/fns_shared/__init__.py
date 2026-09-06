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


def _default_dashboard_store(hass: HomeAssistant):
    """Vrátí úložiště výchozího dashboardu napříč verzemi HA."""
    lovelace = hass.data.get("lovelace")
    if lovelace is None:
        return None
    dashboards = getattr(lovelace, "dashboards", None)
    if dashboards is None and isinstance(lovelace, dict):
        dashboards = lovelace.get("dashboards")
    if not dashboards:
        return None
    return dashboards.get(None)


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

    async def _deploy_sun_card(_call: ServiceCall) -> None:
        store = _default_dashboard_store(hass)
        if store is None:
            raise ValueError("výchozí dashboard není ve storage režimu")
        card = await hass.async_add_executor_job(_load_sun_card)
        dashboard = await store.async_load(False)
        where = _replace_sun_card(dashboard, card)
        await store.async_save(dashboard)
        _LOGGER.info("%s: karta slunce %s", DOMAIN, where)

    hass.services.async_register(DOMAIN, SERVICE_DEPLOY_SUN_CARD, _deploy_sun_card)

    if hass.state is CoreState.running:  # reload integrace za chodu
        await _apply()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _apply)
    return True
