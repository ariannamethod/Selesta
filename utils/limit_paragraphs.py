def limit_paragraphs(text, max_paragraphs=4):
    """Обрезает текст до N абзацев (по пустой строке или переводу строки)."""
    paras = [p.strip() for p in text.replace('\r', '').split('\n\n') if p.strip()]
    limited = paras[:max_paragraphs]
    return '\n\n'.join(limited)
