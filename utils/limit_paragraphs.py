def limit_paragraphs(text, max_paragraphs=3):
    paragraphs = text.split('\n')
    limited = []
    count = 0
    for p in paragraphs:
        if p.strip():
            count += 1
            limited.append(p)
        if count >= max_paragraphs:
            break
    return '\n'.join(limited)
