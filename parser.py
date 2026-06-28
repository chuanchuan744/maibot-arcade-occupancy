import re

from .models import ArcadeConfig, ParsedCommand


def parse_message(
    text: str, summary_aliases: list[str], arcades: list[ArcadeConfig]
) -> ParsedCommand:
    content = text.strip()
    if content in summary_aliases:
        return ParsedCommand(kind="summary", query=content)

    enabled_arcades = [arcade for arcade in arcades if arcade.enabled]

    query_patterns = [
        (alias, arcade.name)
        for arcade in enabled_arcades
        for alias in arcade.query_aliases
    ]
    for alias, arcade_name in sorted(
        query_patterns, key=lambda item: len(item[0]), reverse=True
    ):
        if content == alias:
            return ParsedCommand(kind="query", arcade_name=arcade_name, query=content)

    for alias, arcade_name in sorted(
        query_patterns, key=lambda item: len(item[0]), reverse=True
    ):
        if content == f"清空{alias}":
            return ParsedCommand(kind="clear", arcade_name=arcade_name, query=content)

    if content == "清空全部":
        return ParsedCommand(kind="clear_all", query=content)

    update_patterns = [
        (alias, arcade.name)
        for arcade in enabled_arcades
        for alias in arcade.update_aliases
    ]
    for alias, arcade_name in sorted(
        update_patterns, key=lambda item: len(item[0]), reverse=True
    ):
        match = re.fullmatch(rf"{re.escape(alias)}(?:\s*=\s*|\s+)?(\d+)", content)
        if match:
            return ParsedCommand(
                kind="update",
                arcade_name=arcade_name,
                query=content,
                count=int(match.group(1)),
            )

    return ParsedCommand(kind="none", query=content)
