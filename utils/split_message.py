import re

def limit_paragraphs(text, max_paragraphs=4):
    """
    Trims the input text to at most N paragraphs.
    A paragraph is considered as a block separated by empty lines or newlines.
    """
    # Split by double newlines, bullet points, or at least by single \n if everything is glued together.
    paragraphs = re.split(r'(?:\n\s*\n|\r\n\s*\r\n|(?<=\n)-\s|\r\s*\r)', text)
    if len(paragraphs) == 1:
        paragraphs = text.split('\n')
    limited = [p.strip() for p in paragraphs if p.strip()][:max_paragraphs]
    if not limited:
        return "[Empty response. Selesta could not extract any content.]"
    return '\n\n'.join(limited)
