"""Platform for sensor integration."""
from __future__ import annotations
import csv
from zoneinfo import ZoneInfo

import requests
import logging

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from datetime import datetime, timedelta, timezone

SCAN_INTERVAL = timedelta(seconds=20)
_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, config_entry, async_add_entities):
    """Konfiguracja za pomcą przepływu konfiguracji."""
    
    """This one is in use"""
    async_add_entities([PSECalendar(2, "PSE Oszczedzanie"),
                        PSECalendar(0, "PSE Uzywanie")])


class PSECalendar(CalendarEntity):
    """Representation of a Sensor."""
    

    def __init__(self, search, name) -> None:
        _LOGGER.info("PSE constructor"+name)
        super().__init__()
        self.ev = []
        self.cr_time = None
        self.last_update = None
        self.cloud_response = None
        self.last_network_pull = datetime(
            year=2000, month=1, day=1, tzinfo=timezone.utc
        )
        self._attr_unique_id = name.replace(" ", "_")
        self._attr_name = name
        self.searchKey = search


    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime.datetime,
        end_date: datetime.datetime,
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range."""
        ret = []
        ev: CalendarEvent
        for ev in self.ev:
            if (
                start_date < ev.start
                and ev.start < end_date
                or start_date < ev.start
                and ev.end < end_date
                or start_date < ev.end
                and ev.end < end_date
            ):
                ret.append(ev)
        return ret

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming event."""

        ev: CalendarEvent
        for ev in self.ev:
            if datetime.now(ZoneInfo(self.hass.config.time_zone)) < ev.end:
                return ev

    def fetch_cloud_data(self):
        now = datetime.now()
        url = f"https://api.raporty.pse.pl/api/pdgsz?$filter=business_date ge '{now.strftime('%Y-%m-%d')}'"
        try:
            self.cloud_response = requests.get( url, timeout=10)
            self.cloud_response.encoding = 'ISO-8859-2'
        except ReadTimeout:
            self.cloud_response = ""


    def json_to_ev(self, json):
        description="https://raporty.pse.pl/?report=PDGSZ&state=Funkcjonowanie%20KSE,Plany%20pracy%20KSE,Ograniczenia%20sieciowe,Funkcjonowanie%20RB"
        event_start = None
        tz = ZoneInfo(self.hass.config.time_zone)
        for i in json["value"]:
            if self.searchKey == i['znacznik'] :
                if event_start is None:
                    event_start = datetime.strptime(i['udtczas'],"%Y-%m-%d %H:%M").replace(tzinfo=tz)
            else:
                if not event_start is None:
                    self.ev.append(
                        CalendarEvent(
                            event_start,
                            datetime.strptime(i['udtczas'],"%Y-%m-%d %H:%M").replace(tzinfo=tz)-timedelta(seconds=1),
                            self._attr_name,
                            description=description
                        )
                    )
                    event_start = None
        if not event_start is None:
            self.ev.append(
                CalendarEvent(
                    event_start,
                    datetime.strptime(i['udtczas'],"%Y-%m-%d %H:%M").replace(tzinfo=tz)+ timedelta(hours=1),
                    self._attr_name,
                    description=description
                )
            )


    async def async_update(self):
        """Retrieve latest state."""
        now = datetime.now(ZoneInfo(self.hass.config.time_zone))
        if now < self.last_network_pull + timedelta(minutes=30):
            return
        self.last_network_pull = now
        self.cloud_response = None
        await self.hass.async_add_executor_job(self.fetch_cloud_data)

        if self.cloud_response is None or self.cloud_response.status_code != 200:
            return False
        self.ev.clear()

        self.json_to_ev(self.cloud_response.json())

