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
    async_add_entities([PSECalendar("NE O", "PSE Oszczedzanie"), 
                        PSECalendar("ZALECANE U", "PSE Uzywanie")])


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
        """fetch today data"""
        now = datetime.now(ZoneInfo(self.hass.config.time_zone))
        try:
            self.cloud_response = requests.get(
                f"https://www.pse.pl/getcsv/-/export/csv/PL_GS/data/{now.strftime('%Y%m%d')}",
                timeout=10,
            )
            self.cloud_response.encoding = 'ISO-8859-2'

        except ReadTimeout:
            self.cloud_response = ""

    def fetch_cloud_data_1(self):
        """fetch tomorrow data"""
        now = datetime.now(ZoneInfo(self.hass.config.time_zone)) + timedelta(days=1)
        try:
            self.cloud_response = requests.get(
                f"https://www.pse.pl/getcsv/-/export/csv/PL_GS/data/{now.strftime('%Y%m%d')}",
                timeout=10,
            )
            self.cloud_response.encoding = 'ISO-8859-2'
        except requests.exceptions.ReadTimeout:
            self.cloud_response = ""

    def csv_to_events(self, csv_reader: csv, day: datetime):
        """Transform csv to events"""
        event_start = None
        descr = None
        for row in csv_reader:
            if self.searchKey in row[3]:
                if event_start is None:
                    event_start = int(row[1])
                    descr = row[3]
            else:
                if not event_start is None:
                    self.ev.append(
                        CalendarEvent(
                            day.replace(hour=event_start),
                            day.replace(hour=int(row[1])),
                            descr,
                            description="https://www.pse.pl/dane-systemowe/plany-pracy-kse/godziny-szczytu",
                        )
                    )
                    event_start = None
                    descr = None
        if not event_start is None:
            self.ev.append(
                CalendarEvent(
                    day.replace(hour=event_start),
                    day.replace(hour=0) + timedelta(days=1),
                    descr,
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

        csv_output = csv.reader(self.cloud_response.text.splitlines(), delimiter=";")
        now = now.replace(minute=0).replace(second=0)
        self.csv_to_events(csv_output, now)

        self.cloud_response = None
        await self.hass.async_add_executor_job(self.fetch_cloud_data_1)

        if self.cloud_response is None or self.cloud_response.status_code != 200:
            return False

        csv_output = csv.reader(self.cloud_response.text.splitlines(), delimiter=";")
        now = now.replace(minute=0).replace(second=0) + timedelta(days=1)
        self.csv_to_events(csv_output, now)
