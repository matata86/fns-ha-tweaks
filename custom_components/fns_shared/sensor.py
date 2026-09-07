"""Senzory východu a západu Měsíce.

Domácí instance je používá v kartě sluneční linky, kde se čas do té doby
odhadoval ze stáří Měsíce („východ slunce + 50 min × stáří"). Odhad se
běžně mýlil o hodiny, tyhle senzory sedí na minuty.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.util import dt as dt_util

from .moon import events, illumination

_LOGGER = logging.getLogger(__name__)

SCAN = timedelta(minutes=10)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Založí dvojici senzorů; polohu bere z konfigurace Home Assistantu."""
    if discovery_info is None:
        return
    entities = [
        MoonEventSensor(hass, rising=True),
        MoonEventSensor(hass, rising=False),
        MoonIlluminationSensor(),
    ]
    async_add_entities(entities, True)

    async def _refresh(_now) -> None:
        for entity in entities:
            entity.async_schedule_update_ha_state(True)

    async_track_time_interval(hass, _refresh, SCAN)


class MoonEventSensor(SensorEntity):
    """Nejbližší budoucí východ (nebo západ) Měsíce."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, rising: bool) -> None:
        self._hass = hass
        self._rising = rising
        self._attr_name = "Východ Měsíce" if rising else "Západ Měsíce"
        self._attr_unique_id = f"fns_shared_moon_{'rise' if rising else 'set'}"
        self._attr_icon = "mdi:moon-waning-crescent"
        self._today: datetime | None = None
        self._tomorrow: datetime | None = None

    def _events(self, day: date):
        return events(
            day,
            self._hass.config.latitude,
            self._hass.config.longitude,
            dt_util.get_default_time_zone(),
        )

    def _pick(self, day: date) -> datetime | None:
        rise, setting = self._events(day)
        return rise if self._rising else setting

    async def async_update(self) -> None:
        now = dt_util.now()
        today = now.date()
        self._today = await self._hass.async_add_executor_job(self._pick, today)
        self._tomorrow = await self._hass.async_add_executor_job(
            self._pick, today + timedelta(days=1)
        )

        # Stav = nejbližší budoucí událost. Měsíc některý den nevyjde vůbec
        # (východ se posouvá o ~50 min denně a jednou za měsíc přeskočí půlnoc),
        # proto se prohledává i pár dalších dnů.
        if self._today and self._today > now:
            self._attr_native_value = self._today
            return
        if self._tomorrow and self._tomorrow > now:
            self._attr_native_value = self._tomorrow
            return
        for offset in range(2, 5):
            found = await self._hass.async_add_executor_job(
                self._pick, today + timedelta(days=offset)
            )
            if found and found > now:
                self._attr_native_value = found
                return
        self._attr_native_value = None

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Dnešní a zítřejší událost — karta z nich kreslí pás nad obzorem."""
        return {
            "dnes": self._today.isoformat() if self._today else None,
            "zitra": self._tomorrow.isoformat() if self._tomorrow else None,
        }


class MoonIlluminationSensor(SensorEntity):
    """Osvětlená část měsíčního kotouče v procentech.

    Karta ji dřív odhadovala z osmi fází, což u srpku dávalo 4 % místo 17 %.
    """

    _attr_name = "Osvětlení Měsíce"
    _attr_unique_id = "fns_shared_moon_illumination"
    _attr_icon = "mdi:brightness-percent"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_should_poll = False

    async def async_update(self) -> None:
        self._attr_native_value = round(illumination(dt_util.now()), 1)
