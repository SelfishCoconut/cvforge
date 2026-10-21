"""Fence untrusted text as data before it goes into a prompt (NFR-07)."""


def fence(tag: str, text: str) -> str:
    """Wrap `text` in `<tag>` tags so it reads as data and cannot close its own fence.

    Every `<` in the text is escaped in one linear pass, so no tag can be written or
    rebuilt inside it.

    Args:
        tag: The fence's tag name, which the prompt tells the model to treat as data.
        text: The untrusted text.

    Returns:
        The fenced text.
    """
    return f"<{tag}>\n{text.replace('<', '&lt;')}\n</{tag}>"
