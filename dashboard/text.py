"""Show untrusted text (pilot notes, log messages, LLM output) as plain text in Streamlit markdown."""
import re

MARKDOWN_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+\-.!|<>~:$])")


def plain(text) -> str:
    """Escape markdown, so an image or link in the text is shown, never loaded or followed."""
    return MARKDOWN_SPECIAL.sub(r"\\\1", str(text))
