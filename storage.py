import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .models import ArcadeState


class JsonStateStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load_states(self) -> dict[str, ArcadeState]:
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps({"version": 1, "arcades": {}}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return {}

        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            backup = self.path.with_name(
                f"{self.path.name}.bak.{datetime.now().strftime('%Y%m%d%H%M%S')}"
            )
            self.path.replace(backup)
            self.path.write_text(
                json.dumps({"version": 1, "arcades": {}}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return {}

        return {
            name: ArcadeState(**data)
            for name, data in payload.get("arcades", {}).items()
        }

    def save_states(self, states: dict[str, ArcadeState]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "arcades": {name: asdict(state) for name, state in states.items()},
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )


class JsonCooldownStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load_cooldowns(self) -> dict[str, dict[str, str]]:
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(
                    {"version": 1, "query": {}, "update": {}},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            return {"query": {}, "update": {}}

        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            backup = self.path.with_name(
                f"{self.path.name}.bak.{datetime.now().strftime('%Y%m%d%H%M%S')}"
            )
            self.path.replace(backup)
            self.path.write_text(
                json.dumps(
                    {"version": 1, "query": {}, "update": {}},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            return {"query": {}, "update": {}}

        return {
            "query": {
                str(user_id): str(timestamp)
                for user_id, timestamp in payload.get("query", {}).items()
            },
            "update": {
                str(user_id): str(timestamp)
                for user_id, timestamp in payload.get("update", {}).items()
            },
        }

    def save_cooldowns(self, cooldowns: dict[str, dict[str, str]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "query": cooldowns.get("query", {}),
            "update": cooldowns.get("update", {}),
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
