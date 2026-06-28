from dataclasses import dataclass, field
from typing import Literal


CommandKind = Literal["summary", "query", "update", "clear", "clear_all", "none"]


@dataclass(frozen=True)
class ArcadeConfig:
    name: str
    enabled: bool
    query_aliases: list[str]
    update_aliases: list[str]
    open_time: str
    close_time: str


@dataclass(frozen=True)
class ParsedCommand:
    kind: CommandKind
    arcade_name: str | None = None
    query: str = ""
    count: int | None = None


@dataclass(frozen=True)
class TemplateBundle:
    single_open_with_data: str
    single_open_no_data: str
    single_closed: str
    single_not_open: str
    update_success: str
    permission_denied: str
    rate_limited: str
    summary_wrapper: str
    summary_line_open_with_data: str
    summary_line_open_no_data: str
    summary_line_closed: str
    summary_line_not_open: str


@dataclass
class ArcadeState:
    count: int
    updated_at: str
    updated_by_name: str
    updated_by_qq: str
    updated_in_chat: str


@dataclass
class RuntimeState:
    arcades: dict[str, ArcadeState] = field(default_factory=dict)


DEFAULT_TEMPLATE_BUNDLE = TemplateBundle(
    single_open_with_data="当前{arcade_name}人数为{count}\n登记人：{user_name}（{user_qq}）\n更新时间：{updated_time}",
    single_open_no_data="{arcade_name}当前无数据",
    single_closed="{arcade_name}已闭店",
    single_not_open="{arcade_name}未开店",
    update_success="已更新{arcade_name}人数为{count}\n登记人：{user_name}（{user_qq}）\n更新时间：{updated_time}",
    permission_denied="你无权限使用此功能",
    rate_limited="操作过快，请 {remaining_seconds} 秒后再试",
    summary_wrapper="排卡信息\n{all_lines}",
    summary_line_open_with_data="{arcade_name}：{count}人（{user_name} {user_qq}，{updated_time} 更新）",
    summary_line_open_no_data="{arcade_name}：无数据",
    summary_line_closed="{arcade_name}：已闭店",
    summary_line_not_open="{arcade_name}：未开店",
)
