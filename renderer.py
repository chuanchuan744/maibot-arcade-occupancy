from .models import DEFAULT_TEMPLATE_BUNDLE, TemplateBundle


def _safe_format(template: str, fallback: str, variables: dict[str, object]) -> str:
    try:
        return template.format(**variables)
    except KeyError:
        return fallback.format(**variables)


def render_summary_line(
    status: str, templates: TemplateBundle, variables: dict[str, object]
) -> str:
    mapping = {
        "open_with_data": (
            templates.summary_line_open_with_data,
            DEFAULT_TEMPLATE_BUNDLE.summary_line_open_with_data,
        ),
        "open_no_data": (
            templates.summary_line_open_no_data,
            DEFAULT_TEMPLATE_BUNDLE.summary_line_open_no_data,
        ),
        "closed": (
            templates.summary_line_closed,
            DEFAULT_TEMPLATE_BUNDLE.summary_line_closed,
        ),
        "not_open": (
            templates.summary_line_not_open,
            DEFAULT_TEMPLATE_BUNDLE.summary_line_not_open,
        ),
    }
    template, fallback = mapping[status]
    return _safe_format(template, fallback, variables)
