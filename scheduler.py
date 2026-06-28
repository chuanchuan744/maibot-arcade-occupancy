from datetime import datetime, time

from .models import ArcadeConfig, ArcadeState


def _parse_hhmm(value: str) -> time:
    hour, minute = value.split(":")
    return time(hour=int(hour), minute=int(minute))


def evaluate_arcade_status(arcade: ArcadeConfig, now: datetime) -> str:
    current = now.timetz().replace(tzinfo=None)
    open_time = _parse_hhmm(arcade.open_time)
    close_time = _parse_hhmm(arcade.close_time)
    if current < open_time:
        return "not_open"
    if current >= close_time:
        return "closed"
    return "open"


def purge_closed_arcades(
    arcades: list[ArcadeConfig], state: dict[str, ArcadeState], now: datetime
) -> dict[str, ArcadeState]:
    remaining = dict(state)
    for arcade in arcades:
        if evaluate_arcade_status(arcade, now) == "closed":
            remaining.pop(arcade.name, None)
    return remaining
