def split_message(text: str, max_length: int = 4096) -> list[str]:
    """
    Splits a long text into chunks suitable for sending in messages (e.g., Telegram).
    Chunks are split at the nearest newline before max_length if possible.
    """
    if not text:
        return []
    messages = []
    while len(text) > max_length:
        # Try to split at the last newline before max_length
        split_at = text.rfind('\n', 0, max_length)
        if split_at == -1 or split_at < max_length // 2:
            split_at = max_length
        messages.append(text[:split_at].strip())
        text = text[split_at:].lstrip()
    if text:
        messages.append(text)
    return messages
