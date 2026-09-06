"""FNS Shared — sdílené části dvou instancí Home Assistantu.

Integrace se instaluje přes HACS, takže se nová verze nabídne k aktualizaci jako
u kteréhokoli jiného repozitáře. Při startu rozbalí to, co s sebou nese:

- motiv ``fns-mushroom`` do ``themes/fns-mushroom/fns-mushroom.yaml``
- sdílené UIX foundries do ``uix/fns_shared.yaml`` a zaregistruje je v UIX

Do ``configuration.yaml`` stačí řádek ``fns_shared:``.
"""

from __future__ import annotations

import logging
import os
import shutil

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, Event, HomeAssistant
from homeassistant.helpers.typing import ConfigType

DOMAIN = "fns_shared"
UIX_DOMAIN = "uix"
UIX_CONF_FOUNDRY_FILES = "foundry_files"

THEME_SOURCE = "theme/fns-mushroom.yaml"
THEME_TARGET = "themes/fns-mushroom/fns-mushroom.yaml"
FOUNDRIES_SOURCE = "foundries/fns_shared.yaml"
FOUNDRIES_TARGET = "uix/fns_shared.yaml"

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


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Nasadí sdílené soubory a po startu HA je nechá načíst."""

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

    if hass.state is CoreState.running:  # HA už běží (reload integrace za chodu)
        await _apply()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _apply)
    return True
