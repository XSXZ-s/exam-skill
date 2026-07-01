import re


def normalize_markdown_formulas(markdown: str) -> str:
    markdown = _normalize_display_brackets(markdown)
    markdown = _normalize_inline_brackets(markdown)
    markdown = _normalize_math_contents(markdown)
    return markdown


def _normalize_display_brackets(markdown: str) -> str:
    return re.sub(
        r"\\\[\s*(.*?)\s*\\\]",
        lambda match: f"$$\n{_normalize_math_expression(match.group(1))}\n$$",
        markdown,
        flags=re.S,
    )


def _normalize_inline_brackets(markdown: str) -> str:
    return re.sub(
        r"\\\((.+?)\\\)",
        lambda match: f"${_normalize_math_expression(match.group(1))}$",
        markdown,
    )


def _normalize_math_contents(markdown: str) -> str:
    markdown = re.sub(
        r"\$\$\s*(.*?)\s*\$\$",
        lambda match: f"$$\n{_normalize_math_expression(match.group(1))}\n$$",
        markdown,
        flags=re.S,
    )
    return re.sub(
        r"(?<!\\)\$([^$\n]+?)(?<!\\)\$",
        lambda match: f"${_normalize_math_expression(match.group(1))}$",
        markdown,
    )


def _normalize_math_expression(expression: str) -> str:
    expression = expression.strip()
    expression = expression.replace(r"\times", "×").replace(r"\cdot", "×")
    expression = re.sub(r"(?<=\S)\s*\*\s*(?=\S)", "×", expression)
    return expression
