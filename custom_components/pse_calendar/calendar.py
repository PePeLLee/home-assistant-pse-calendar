"""Platform for sensor integration."""
from __future__ import annotations
import csv
from zoneinfo import ZoneInfo

import requests

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from datetime import datetime, timedelta

SCAN_INTERVAL = timedelta(minutes=30)


def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the sensor platform."""
    add_entities([PSECalendar()])


async def async_setup_entry(hass: HomeAssistant, config_entry, async_add_entities):
    """Konfiguracja za pomcą przepływu konfiguracji."""
    async_add_entities([PSECalendar()])


class PSECalendar(CalendarEntity):
    """Representation of a Sensor."""

    _attr_unique_id = "pse_calendar"

    def __init__(self) -> None:
        super().__init__()
        self.ev = []
        self.cr_time = None
        self.last_update = None
        self.cloud_response = None

    _attr_name = "PSE Calendar"

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
        self.cloud_response = requests.get(
            f"https://www.pse.pl/getcsv/-/export/csv/PL_GS/data/{now.strftime('%Y%m%d')}",
            timeout=10,
        )

    def fetch_cloud_data_1(self):
        """fetch tomorrow data"""
        now = datetime.now(ZoneInfo(self.hass.config.time_zone)) + timedelta(days=1)
        self.cloud_response = requests.get(
            f"https://www.pse.pl/getcsv/-/export/csv/PL_GS/data/{now.strftime('%Y%m%d')}",
            timeout=10,
        )

    def csv_to_events(self, csv_reader: csv, day: datetime):
        """Transform csv to events"""
        event_start = None
        for row in csv_reader:
            if row[3].startswith("ZALEC"):
                if event_start is None:
                    event_start = int(row[1])
            else:
                if not event_start is None:
                    self.ev.append(
                        CalendarEvent(
                            day.replace(hour=event_start),
                            day.replace(hour=int(row[1])),
                            "Reduce usage",
                            description="https://www.pse.pl/dane-systemowe/plany-pracy-kse/godziny-szczytu",
                        )
                    )
                    event_start = None
        if not event_start is None:
            self.ev.append(
                CalendarEvent(
                    day.replace(hour=event_start),
                    day.replace(hour=0) + timedelta(days=1),
                    "Reduce usage",
                )
            )

    async def async_update(self):
        """Retrieve latest state."""
        now = datetime.now(ZoneInfo(self.hass.config.time_zone))
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
