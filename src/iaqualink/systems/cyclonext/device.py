from __future__ import annotations

import logging
from enum import Enum, unique
from typing import TYPE_CHECKING, Any, cast

from iaqualink.device import (
    AqualinkDevice,
    AqualinkSensor,
    AqualinkSwitch,
    AqualinkThermostat,
)
from iaqualink.exception import AqualinkInvalidParameterException

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from iaqualink.systems.cyclonext.system import CyclonextSystem
    from iaqualink.typing import DeviceData

LOGGER = logging.getLogger("iaqualink")


@unique
class CyclonextState(Enum):
    OFF = 0
    ON = 1


class CyclonextDevice(AqualinkDevice):
    def __init__(self, system: CyclonextSystem, data: DeviceData):
        super().__init__(system, data)

        # This silences mypy errors due to AqualinkDevice type annotations.
        self.system: CyclonextSystem = system

    @property
    def label(self) -> str:
        name = self.name
        return " ".join([x.capitalize() for x in name.split("_")])

    @property
    def state(self) -> str:
        return str(self.data["state"])

    @property
    def name(self) -> str:
        return self.data["name"]

    @property
    def manufacturer(self) -> str:
        return "Zodiac"

    @property
    def model(self) -> str:
        return self.__class__.__name__.replace("Cyclonext", "")

    @classmethod
    def from_data(
        cls, system: CyclonextSystem, data: DeviceData
    ) -> CyclonextDevice:
        class_: type[CyclonextDevice]

        if data["name"] in ["production", "boost", "low"]:
            class_ = CyclonextProg
        else:
            class_ = CyclonextAttributeSensor

        return class_(system, data)


class CyclonextSensor(CyclonextDevice, AqualinkSensor):
    """These sensors are called sns_#."""

    @property
    def is_on(self) -> bool:
        return CyclonextState(self.data["state"]) == CyclonextState.ON

    @property
    def state(self) -> str:
        if self.is_on:
            return str(self.data["value"])
        return ""

    @property
    def label(self) -> str:
        return self.data["sensor_type"]

    @property
    def name(self) -> str:
        # XXX: We're using the label as name rather than "sns_#".
        # Might revisit later.
        return self.data["sensor_type"].lower().replace(" ", "_")


class CyclonextAttributeSensor(CyclonextDevice, AqualinkSensor):
    """These sensors are a simple key/value in equipment->robot."""


# This is an abstract class, not to be instantiated directly.
class CyclonextProg(CyclonextAttributeSensor):
    @property
    def _command(self) -> Callable[[str, int], Coroutine[Any, Any, None]]:
        return self.system
