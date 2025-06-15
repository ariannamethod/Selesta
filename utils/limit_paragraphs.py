def limit_paragraphs(text, max_paragraphs=4):
    """
    Limits the text to a maximum number of paragraphs.
    """
    paras = [p.strip() for p in text.replace('\r', '').split('\n\n') if p.strip()]
    limited = paras[:max_paragraphs]
    if not limited:
        return "[No content to display.]"
    return '\n\n'.join(limited)
