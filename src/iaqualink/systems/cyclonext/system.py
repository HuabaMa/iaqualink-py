from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from iaqualink.const import MIN_SECS_TO_REFRESH
from iaqualink.exception import (
    AqualinkServiceException,
    AqualinkServiceUnauthorizedException,
    AqualinkSystemOfflineException,
)
from iaqualink.system import AqualinkSystem
from iaqualink.systems.cyclonext.device import CyclonextDevice

if TYPE_CHECKING:
    import httpx

    from iaqualink.client import AqualinkClient
    from iaqualink.typing import Payload

CYCLONEXT_DEVICES_URL = "https://prod.zodiac-io.com/devices/v1"


LOGGER = logging.getLogger("iaqualink")


class CyclonextSystem(AqualinkSystem):
    NAME = "cyclonext"

    def __init__(self, aqualink: AqualinkClient, data: Payload):
        super().__init__(aqualink, data)
        # This lives in the parent class but mypy complains.
        self.last_refresh: int = 0
        self.temp_unit = "C"  # TODO: check if unit can be changed on panel?

    def __repr__(self) -> str:
        attrs = ["name", "serial", "data"]
        attrs = [f"{i}={getattr(self, i)!r}" for i in attrs]
        return f"{self.__class__.__name__}({' '.join(attrs)})"

    async def send_devices_request(self, **kwargs: Any) -> httpx.Response:
        url = f"{CYCLONEXT_DEVICES_URL}/{self.serial}/shadow"
        headers = {"Authorization": self.aqualink.id_token}

        try:
            r = await self.aqualink.send_request(url, headers=headers, **kwargs)
        except AqualinkServiceUnauthorizedException:
            # token expired so refresh the token and try again
            await self.aqualink.login()
            headers = {"Authorization": self.aqualink.id_token}
            r = await self.aqualink.send_request(url, headers=headers, **kwargs)

        return r

    async def send_reported_state_request(self) -> httpx.Response:
        return await self.send_devices_request()

    async def send_desired_state_request(
        self, state: dict[str, Any]
    ) -> httpx.Response:
        return await self.send_devices_request(
            method="post", json={"state": {"desired": state}}
        )

    async def update(self) -> None:
        # Be nice to Aqualink servers since we rely on polling.
        now = int(time.time())
        delta = now - self.last_refresh
        if delta < MIN_SECS_TO_REFRESH:
            LOGGER.debug(f"Only {delta}s since last refresh.")
            return

        try:
            r = await self.send_reported_state_request()
        except AqualinkServiceException:
            self.online = None
            raise

        try:
            self._parse_shadow_response(r)
        except AqualinkSystemOfflineException:
            self.online = False
            raise

        self.online = True
        self.last_refresh = int(time.time())

    def _parse_shadow_response(self, response: httpx.Response) -> None:
        data = response.json()

        LOGGER.debug(f"Shadow response: {data}")

        devices = {}

        # Process the robot attributes[equipment]
        # Make the data a bit flatter.
        root = data["state"]["reported"]["equipment"]["robot"]

        for idx, value in enumerate(root):
            if value is None:
                continue

            #only a few pieces of information are evaluated.
            for name, state in value.items():
                if name in (["mode", "cycle", "cycleStartTime"]):
                    attrs = {"name": name}
                    attrs.update({"state": state})
                    devices.update({name: attrs})

                if name == "durations":
                    for durName, durState in state.items():
                        if durName in (["quickTim", "deepTim", "stepper"]):
                            attrs = {"name": durName}
                            attrs.update({"state": durState})
                            devices.update({durName: attrs})

        LOGGER.debug(f"devices: {devices}")

        for k, v in devices.items():
            if k in self.devices:
                for dk, dv in v.items():
                    self.devices[k].data[dk] = dv
            else:
                self.devices[k] = CyclonextDevice.from_data(self, v)
