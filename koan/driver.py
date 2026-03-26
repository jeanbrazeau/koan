# Driver stub -- the main FSM that coordinates phase transitions.
# Expanded in T5; for now it just waits for the start event.

from __future__ import annotations

from typing import TYPE_CHECKING

from .logger import get_logger

if TYPE_CHECKING:
    from .state import AppState


async def driver_main(app_state: AppState) -> None:
    log = get_logger("driver")
    log.info("Driver waiting for start event...")
    await app_state.start_event.wait()
    log.info("Start event received -- driver FSM not yet implemented (T5)")
