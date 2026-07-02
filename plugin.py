from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
import re
from pathlib import Path
from typing import Any, Mapping

try:
    from maibot_sdk import Command, Field, MaiBotPlugin, PluginConfigBase
except ImportError:  # pragma: no cover - local test fallback
    class PluginConfigBase:  # type: ignore[no-redef]
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

    class MaiBotPlugin:  # type: ignore[no-redef]
        pass

    def Command(*_args, **_kwargs):  # type: ignore[no-redef]
        def decorator(func):
            return func

        return decorator

    def Field(default=None, default_factory=None, **_kwargs):  # type: ignore[no-redef]
        if default_factory is not None:
            return default_factory()
        return default

from .models import ArcadeConfig, ArcadeState, TemplateBundle
from .parser import parse_message
from .renderer import render_summary_line
from .scheduler import evaluate_arcade_status, purge_closed_arcades
from .storage import JsonCooldownStore, JsonStateStore


@dataclass
class CommandResult:
    reply: str | None
    states: dict[str, ArcadeState]
    cooldowns: dict[str, dict[str, str]]


def _normalize_alias_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [
            item.strip()
            for item in re.split("[\\s,\uFF0C]+", value.strip())
            if item.strip()
        ]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []


def _preprocess_arcade_alias_config(
    config_data: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], bool]:
    raw_config: dict[str, Any] = (
        dict(config_data) if isinstance(config_data, Mapping) else {}
    )
    general_config = raw_config.get("general")
    if isinstance(general_config, Mapping) and "arcades" in general_config:
        raw_config["arcades"] = general_config["arcades"]
        raw_config["general"] = {
            key: value for key, value in general_config.items() if key != "arcades"
        }
        if not raw_config["general"]:
            raw_config.pop("general", None)
        changed = True
    else:
        changed = False

    arcades = raw_config.get("arcades")
    if not isinstance(arcades, list):
        return raw_config, changed

    normalized_arcades: list[Any] = []
    for arcade in arcades:
        if not isinstance(arcade, Mapping):
            normalized_arcades.append(arcade)
            continue

        arcade_data = dict(arcade)
        for field_name in ("query_aliases", "update_aliases"):
            if field_name not in arcade_data:
                continue
            normalized_value = _normalize_alias_values(arcade_data[field_name])
            if arcade_data[field_name] != normalized_value:
                arcade_data[field_name] = normalized_value
                changed = True
        normalized_arcades.append(arcade_data)

    if changed:
        raw_config["arcades"] = normalized_arcades
    return raw_config, changed


def _patch_arcades_webui_schema(schema: dict[str, Any]) -> dict[str, Any]:
    if not schema:
        return schema

    patched_schema = deepcopy(schema)
    arcades_field = (
        patched_schema.get("sections", {})
        .get("general", {})
        .get("fields", {})
        .get("arcades")
    )
    if not isinstance(arcades_field, dict):
        return patched_schema

    item_fields = arcades_field.get("item_fields")
    if not isinstance(item_fields, dict):
        return patched_schema

    patched_schema["sections"]["general"]["name"] = "."

    for field_name in ("query_aliases", "update_aliases"):
        field_def = item_fields.get(field_name)
        if not isinstance(field_def, dict):
            continue

        default_value = field_def.get("default")
        if isinstance(default_value, list):
            default_text = ", ".join(
                str(item).strip() for item in default_value if str(item).strip()
            )
        elif default_value is None:
            default_text = ""
        else:
            default_text = str(default_value).strip()

        patched_field = dict(field_def)
        patched_field["type"] = "string"
        patched_field.pop("item_type", None)
        patched_field.pop("item_fields", None)
        patched_field["default"] = default_text
        patched_field["placeholder"] = "多个别名用逗号、空格或换行分隔"

        description = str(patched_field.get("description") or "").strip()
        helper_text = "多个别名用逗号、空格或换行分隔"
        patched_field["description"] = (
            f"{description}；{helper_text}" if description else helper_text
        )
        item_fields[field_name] = patched_field

    return patched_schema


def _remaining_seconds(last_seen: str, now: datetime, cooldown_seconds: int) -> int:
    elapsed = (now - datetime.fromisoformat(last_seen)).total_seconds()
    return max(0, cooldown_seconds - int(elapsed))


def _check_cooldown(
    bucket: dict[str, str], user_id: str, now: datetime, cooldown_seconds: int
) -> int:
    if user_id not in bucket:
        return 0
    return _remaining_seconds(bucket[user_id], now, cooldown_seconds)


def handle_command(
    text: str,
    group_id: str,
    user_id: str,
    user_name: str,
    now: datetime,
    summary_aliases: list[str],
    arcades: list[ArcadeConfig],
    templates: TemplateBundle,
    states: dict[str, ArcadeState],
    allowed_groups: set[str],
    blocked_users: set[str],
    admin_users: set[str],
    block_query: bool,
    block_update: bool,
    cooldowns: dict[str, dict[str, str]],
    enable_query_limit: bool,
    enable_update_limit: bool,
    query_cooldown_seconds: int,
    update_cooldown_seconds: int,
) -> CommandResult:
    if group_id not in allowed_groups:
        return CommandResult(reply=None, states=states, cooldowns=cooldowns)

    parsed = parse_message(text, summary_aliases, arcades)
    clean_states = purge_closed_arcades(arcades, states, now)

    if parsed.kind == "none":
        return CommandResult(reply=None, states=clean_states, cooldowns=cooldowns)

    if user_id in blocked_users:
        if parsed.kind in {"query", "summary"} and block_query:
            return CommandResult(
                reply=templates.permission_denied,
                states=clean_states,
                cooldowns=cooldowns,
            )
        if parsed.kind == "update" and block_update:
            return CommandResult(
                reply=templates.permission_denied,
                states=clean_states,
                cooldowns=cooldowns,
            )

    if parsed.kind in {"clear", "clear_all"}:
        if user_id not in admin_users:
            return CommandResult(
                reply=getattr(templates, "admin_denied", templates.permission_denied),
                states=clean_states,
                cooldowns=cooldowns,
            )
        if parsed.kind == "clear_all":
            return CommandResult(
                reply=getattr(templates, "clear_all_success", "已清空全部机厅数据"),
                states={},
                cooldowns=cooldowns,
            )
        arcade = next(arcade for arcade in arcades if arcade.name == parsed.arcade_name)
        new_states = dict(clean_states)
        new_states.pop(arcade.name, None)
        return CommandResult(
            reply=getattr(templates, "clear_success", "已清空{arcade_name}的数据").format(
                arcade_name=arcade.name
            ),
            states=new_states,
            cooldowns=cooldowns,
        )

    if parsed.kind in {"query", "summary"} and enable_query_limit:
        remaining = _check_cooldown(
            cooldowns["query"], user_id, now, query_cooldown_seconds
        )
        if remaining:
            return CommandResult(
                reply=templates.rate_limited.format(remaining_seconds=remaining),
                states=clean_states,
                cooldowns=cooldowns,
            )

    if parsed.kind == "update" and enable_update_limit:
        remaining = _check_cooldown(
            cooldowns["update"], user_id, now, update_cooldown_seconds
        )
        if remaining:
            return CommandResult(
                reply=templates.rate_limited.format(remaining_seconds=remaining),
                states=clean_states,
                cooldowns=cooldowns,
            )

    if parsed.kind == "query":
        arcade = next(arcade for arcade in arcades if arcade.name == parsed.arcade_name)
        status = evaluate_arcade_status(arcade, now)
        if status == "closed":
            return CommandResult(
                reply=templates.single_closed.format(arcade_name=arcade.name),
                states=clean_states,
                cooldowns=cooldowns,
            )
        if status == "not_open":
            return CommandResult(
                reply=templates.single_not_open.format(arcade_name=arcade.name),
                states=clean_states,
                cooldowns=cooldowns,
            )
        state = clean_states.get(arcade.name)
        if state is None:
            return CommandResult(
                reply=templates.single_open_no_data.format(arcade_name=arcade.name),
                states=clean_states,
                cooldowns=cooldowns,
            )
        return CommandResult(
            reply=templates.single_open_with_data.format(
                arcade_name=arcade.name,
                count=state.count,
                user_name=state.updated_by_name,
                user_qq=state.updated_by_qq,
                updated_time=datetime.fromisoformat(state.updated_at).strftime("%H:%M:%S"),
            ),
            states=clean_states,
            cooldowns={
                **cooldowns,
                "query": {
                    **cooldowns["query"],
                    user_id: now.isoformat(),
                },
            },
        )

    if parsed.kind == "update":
        arcade = next(arcade for arcade in arcades if arcade.name == parsed.arcade_name)
        status = evaluate_arcade_status(arcade, now)
        if status == "closed":
            return CommandResult(
                reply=templates.single_closed.format(arcade_name=arcade.name),
                states=clean_states,
                cooldowns=cooldowns,
            )
        if status == "not_open":
            return CommandResult(
                reply=templates.single_not_open.format(arcade_name=arcade.name),
                states=clean_states,
                cooldowns=cooldowns,
            )
        new_states = dict(clean_states)
        new_states[arcade.name] = ArcadeState(
            count=parsed.count or 0,
            updated_at=now.isoformat(),
            updated_by_name=user_name,
            updated_by_qq=user_id,
            updated_in_chat=group_id,
        )
        return CommandResult(
            reply=templates.update_success.format(
                arcade_name=arcade.name,
                count=parsed.count or 0,
                user_name=user_name,
                user_qq=user_id,
                updated_time=now.strftime("%H:%M:%S"),
            ),
            states=new_states,
            cooldowns={
                **cooldowns,
                "update": {
                    **cooldowns["update"],
                    user_id: now.isoformat(),
                },
            },
        )

    lines = []
    for arcade in [item for item in arcades if item.enabled]:
        status = evaluate_arcade_status(arcade, now)
        if status == "closed":
            lines.append(render_summary_line("closed", templates, {"arcade_name": arcade.name}))
            continue
        if status == "not_open":
            lines.append(render_summary_line("not_open", templates, {"arcade_name": arcade.name}))
            continue
        state = clean_states.get(arcade.name)
        if state is None:
            lines.append(render_summary_line("open_no_data", templates, {"arcade_name": arcade.name}))
            continue
        lines.append(
            render_summary_line(
                "open_with_data",
                templates,
                {
                    "arcade_name": arcade.name,
                    "count": state.count,
                    "user_name": state.updated_by_name,
                    "user_qq": state.updated_by_qq,
                    "updated_time": datetime.fromisoformat(state.updated_at).strftime("%H:%M:%S"),
                },
            )
        )
    return CommandResult(
        reply=templates.summary_wrapper.format(all_lines="\n".join(lines)),
        states=clean_states,
        cooldowns={
            **cooldowns,
            "query": {
                **cooldowns["query"],
                user_id: now.isoformat(),
            },
        },
    )


class PluginSection(PluginConfigBase):
    enabled: bool = Field(default=True)
    config_version: str = Field(default="1.0.0")
    timezone: str = Field(default="Asia/Shanghai")
    state_file: str = Field(default="state.json")
    cooldown_file: str = Field(default="cooldowns.json")
    log_parse_failures: bool = Field(default=False)


class CommandsSection(PluginConfigBase):
    summary_aliases: list[str] = Field(default_factory=lambda: ["j"])
    show_permission_denied_message: bool = Field(default=True)
    show_rate_limit_message: bool = Field(default=True)


class PermissionsSection(PluginConfigBase):
    allowed_groups: list[str] = Field(default_factory=list)
    blocked_users: list[str] = Field(default_factory=list)
    admin_users: list[str] = Field(default_factory=list)
    block_query: bool = Field(default=False)
    block_update: bool = Field(default=True)


class RateLimitSection(PluginConfigBase):
    enable_query_limit: bool = Field(default=False)
    enable_update_limit: bool = Field(default=True)
    query_cooldown_seconds: int = Field(default=10)
    update_cooldown_seconds: int = Field(default=10)
    scope: str = Field(default="per_user")


class TemplatesSection(PluginConfigBase):
    single_open_with_data: str = Field(
        default="当前{arcade_name}人数为{count}\n登记人：{user_name}（{user_qq}）\n更新时间：{updated_time}"
    )
    single_open_no_data: str = Field(default="{arcade_name}当前无数据")
    single_closed: str = Field(default="{arcade_name}已闭店")
    single_not_open: str = Field(default="{arcade_name}未开店")
    update_success: str = Field(
        default="已更新{arcade_name}人数为{count}\n登记人：{user_name}（{user_qq}）\n更新时间：{updated_time}"
    )
    permission_denied: str = Field(default="你无权限使用此功能")
    rate_limited: str = Field(default="操作过快，请 {remaining_seconds} 秒后再试")
    summary_wrapper: str = Field(default="排卡信息\n{all_lines}")
    summary_line_open_with_data: str = Field(
        default="{arcade_name}：{count}人（{user_name} {user_qq}，{updated_time} 更新）"
    )
    summary_line_open_no_data: str = Field(default="{arcade_name}：无数据")
    summary_line_closed: str = Field(default="{arcade_name}：已闭店")
    summary_line_not_open: str = Field(default="{arcade_name}：未开店")
    clear_success: str = Field(default="已清空{arcade_name}的数据")
    clear_all_success: str = Field(default="已清空全部机厅数据")
    admin_denied: str = Field(default="你没有管理员权限")


class ArcadeEntry(PluginConfigBase):
    name: str = Field(default="嘉定信业店")
    enabled: bool = Field(default=True)
    query_aliases: list[str] = Field(default_factory=lambda: ["xyj"])
    update_aliases: list[str] = Field(default_factory=lambda: ["xy"])
    open_time: str = Field(default="10:00")
    close_time: str = Field(default="22:00")


def _default_arcade_entries() -> list[ArcadeEntry]:
    return [
        ArcadeEntry(
            name="嘉定信业店",
            enabled=True,
            query_aliases=["xyj"],
            update_aliases=["xy"],
            open_time="10:00",
            close_time="22:00",
        ),
        ArcadeEntry(
            name="嘉定宝龙店",
            enabled=True,
            query_aliases=["blj"],
            update_aliases=["bl"],
            open_time="10:00",
            close_time="22:00",
        ),
        ArcadeEntry(
            name="六代",
            enabled=True,
            query_aliases=["ldj"],
            update_aliases=["ld"],
            open_time="10:00",
            close_time="22:00",
        ),
        ArcadeEntry(
            name="印象城",
            enabled=True,
            query_aliases=["yxcj"],
            update_aliases=["yxc"],
            open_time="10:00",
            close_time="22:00",
        ),
    ]


class ArcadeOccupancyConfig(PluginConfigBase):
    plugin: PluginSection = Field(default_factory=PluginSection)
    commands: CommandsSection = Field(default_factory=CommandsSection)
    permissions: PermissionsSection = Field(default_factory=PermissionsSection)
    rate_limit: RateLimitSection = Field(default_factory=RateLimitSection)
    templates: TemplatesSection = Field(default_factory=TemplatesSection)
    arcades: list[ArcadeEntry] = Field(default_factory=_default_arcade_entries)


class ArcadeOccupancyPlugin(MaiBotPlugin):
    config_model = ArcadeOccupancyConfig

    def __init__(self) -> None:
        super().__init__()
        self._state_store: JsonStateStore | None = None
        self._cooldown_store: JsonCooldownStore | None = None

    def _data_dir(self) -> Path:
        ctx = getattr(self, "ctx", None)
        paths = getattr(ctx, "paths", None)
        data_dir = getattr(paths, "data_dir", None)
        if data_dir:
            return Path(data_dir).resolve()
        return (Path(__file__).resolve().parent / "data").resolve()

    def _resolve_data_file(self, configured_path: str) -> Path:
        path = Path(configured_path)
        if path.parts and path.parts[0] == "data":
            path = Path(*path.parts[1:])
        data_dir = self._data_dir()
        resolved_path = (path if path.is_absolute() else data_dir / path).resolve()
        try:
            resolved_path.relative_to(data_dir)
        except ValueError as exc:
            raise ValueError("Persistent data files must stay inside data_dir") from exc
        return resolved_path

    async def on_load(self) -> None:
        state_path = self._resolve_data_file(self.config.plugin.state_file)
        cooldown_path = self._resolve_data_file(self.config.plugin.cooldown_file)
        self._state_store = JsonStateStore(state_path)
        self._cooldown_store = JsonCooldownStore(cooldown_path)
        if hasattr(self, "ctx") and hasattr(self.ctx, "logger"):
            self.ctx.logger.info("机厅人数登记插件已加载")

    async def on_unload(self) -> None:
        if hasattr(self, "ctx") and hasattr(self.ctx, "logger"):
            self.ctx.logger.info("机厅人数登记插件已卸载")

    async def on_config_update(self, *args, **kwargs) -> None:
        new_config = kwargs.get("new_config")
        if new_config is None:
            for candidate in reversed(args):
                if isinstance(candidate, ArcadeOccupancyConfig):
                    new_config = candidate
                    break
        if new_config is not None:
            self.config = new_config
        await self.on_load()
        if hasattr(self, "ctx") and hasattr(self.ctx, "logger"):
            self.ctx.logger.info("机厅人数登记插件配置已更新")

    def normalize_plugin_config(
        self, config_data: Mapping[str, Any] | None
    ) -> tuple[dict[str, Any], bool]:
        prepared_config, prepared_changed = _preprocess_arcade_alias_config(config_data)
        parent_normalizer = getattr(super(), "normalize_plugin_config", None)
        if callable(parent_normalizer):
            normalized_config, changed = parent_normalizer(prepared_config)
            return normalized_config, prepared_changed or changed
        return prepared_config, prepared_changed

    def get_webui_config_schema(
        self,
        *,
        plugin_id: str = "",
        plugin_name: str = "",
        plugin_version: str = "",
        plugin_description: str = "",
        plugin_author: str = "",
    ) -> dict[str, Any]:
        parent_getter = getattr(super(), "get_webui_config_schema", None)
        if not callable(parent_getter):
            return {}
        schema = parent_getter(
            plugin_id=plugin_id,
            plugin_name=plugin_name,
            plugin_version=plugin_version,
            plugin_description=plugin_description,
            plugin_author=plugin_author,
        )
        return _patch_arcades_webui_schema(schema)

    def _build_arcades(self) -> list[ArcadeConfig]:
        return [
            ArcadeConfig(
                name=item.name,
                enabled=item.enabled,
                query_aliases=list(item.query_aliases),
                update_aliases=list(item.update_aliases),
                open_time=item.open_time,
                close_time=item.close_time,
            )
            for item in self.config.arcades
        ]

    def _build_templates(self) -> TemplateBundle:
        templates = self.config.templates
        return TemplateBundle(
            single_open_with_data=templates.single_open_with_data,
            single_open_no_data=templates.single_open_no_data,
            single_closed=templates.single_closed,
            single_not_open=templates.single_not_open,
            update_success=templates.update_success,
            permission_denied=templates.permission_denied,
            rate_limited=templates.rate_limited,
            summary_wrapper=templates.summary_wrapper,
            summary_line_open_with_data=templates.summary_line_open_with_data,
            summary_line_open_no_data=templates.summary_line_open_no_data,
            summary_line_closed=templates.summary_line_closed,
            summary_line_not_open=templates.summary_line_not_open,
        )

    @staticmethod
    def _extract_user_name(message: Any) -> str:
        if isinstance(message, dict):
            info = message.get("message_info") or message
            user_info = info.get("user_info") or {}
            direct_candidates = [
                user_info.get("user_cardname"),
                user_info.get("user_nickname"),
                info.get("user_cardname"),
                info.get("user_nickname"),
                message.get("user_cardname"),
                message.get("user_nickname"),
                message.get("nickname"),
                message.get("card"),
            ]
            for candidate in direct_candidates:
                name = str(candidate or "").strip()
                if name:
                    return name

        message_info = getattr(message, "message_info", None)
        user_info = getattr(message_info, "user_info", None)
        object_candidates = [
            getattr(user_info, "user_cardname", None),
            getattr(user_info, "user_nickname", None),
            getattr(message_info, "user_cardname", None),
            getattr(message_info, "user_nickname", None),
            getattr(message, "user_cardname", None),
            getattr(message, "user_nickname", None),
            getattr(message, "nickname", None),
            getattr(message, "card", None),
        ]
        for candidate in object_candidates:
            name = str(candidate or "").strip()
            if name:
                return name

        return "未知用户"

    @Command(
        "arcade_occupancy",
        description="机厅人数登记与查询",
        pattern=r"^(?P<text>.+)$",
    )
    async def handle_group_message(
        self,
        stream_id: str = "",
        group_id: str = "",
        user_id: str = "",
        **kwargs: Any,
    ):
        if not self.config.plugin.enabled or not group_id or not stream_id:
            return False, "插件未启用或不是群聊消息", False

        if self._state_store is None or self._cooldown_store is None:
            await self.on_load()

        matched = kwargs.get("matched_groups") or {}
        text = str(matched.get("text") or "").strip()
        if not text:
            return False, "空消息", False

        states = self._state_store.load_states()
        cooldowns = self._cooldown_store.load_cooldowns()
        result = handle_command(
            text=text,
            group_id=str(group_id),
            user_id=str(user_id),
            user_name=(
                str(kwargs.get("user_name") or "").strip()
                or str(kwargs.get("user_cardname") or "").strip()
                or str(kwargs.get("user_nickname") or "").strip()
                or self._extract_user_name(kwargs.get("message"))
            ),
            now=datetime.now().astimezone(),
            summary_aliases=list(self.config.commands.summary_aliases),
            arcades=self._build_arcades(),
            templates=self._build_templates(),
            states=states,
            allowed_groups={str(item) for item in self.config.permissions.allowed_groups},
            blocked_users={str(item) for item in self.config.permissions.blocked_users},
            admin_users={str(item) for item in self.config.permissions.admin_users},
            block_query=self.config.permissions.block_query,
            block_update=self.config.permissions.block_update,
            cooldowns=cooldowns,
            enable_query_limit=self.config.rate_limit.enable_query_limit,
            enable_update_limit=self.config.rate_limit.enable_update_limit,
            query_cooldown_seconds=self.config.rate_limit.query_cooldown_seconds,
            update_cooldown_seconds=self.config.rate_limit.update_cooldown_seconds,
        )

        self._state_store.save_states(result.states)
        self._cooldown_store.save_cooldowns(result.cooldowns)

        if result.reply is None:
            return False, "消息未命中机厅命令", False

        await self.ctx.send.text(result.reply, stream_id)
        return True, "已处理机厅命令", True


def create_plugin() -> ArcadeOccupancyPlugin:
    return ArcadeOccupancyPlugin()
