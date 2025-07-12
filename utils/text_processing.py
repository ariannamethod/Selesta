from typing import List, Union, Tuple

# Максимальная длина одного сообщения (в символах)
DEFAULT_MAX_MESSAGE_LENGTH = 4096

def process_text(
    text: str, 
    max_length: int = DEFAULT_MAX_MESSAGE_LENGTH,
    split_on_newlines: bool = True
) -> List[str]:
    """
    Простая функция для обработки текста - разбивает длинное сообщение 
    на несколько частей, если оно превышает максимальную длину.
    
    Args:
        text: Текст для обработки
        max_length: Максимальная длина одного сообщения
        split_on_newlines: Предпочтительно разбивать по переводам строк
        
    Returns:
        List[str]: Список частей сообщения
    """
    # Если текст короче максимальной длины, возвращаем как есть
    if len(text) <= max_length:
        return [text]
    
    # Если нужно разбивать по переводам строк
    if split_on_newlines:
        # Разбиваем текст по абзацам
        paragraphs = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
        
        # Собираем абзацы в сообщения
        messages = []
        current_message = ""
        
        for paragraph in paragraphs:
            # Если текущий абзац длиннее максимальной длины, разбиваем его
            if len(paragraph) > max_length:
                # Если текущее сообщение не пустое, добавляем его в список
                if current_message:
                    messages.append(current_message)
                    current_message = ""
                
                # Разбиваем длинный абзац на части
                for i in range(0, len(paragraph), max_length):
                    chunk = paragraph[i:i+max_length]
                    messages.append(chunk)
            # Если абзац помещается в текущее сообщение
            elif len(current_message) + len(paragraph) + 1 <= max_length:  # +1 для '\n'
                if current_message:
                    current_message += "\n" + paragraph
                else:
                    current_message = paragraph
            # Если абзац не помещается в текущее сообщение
            else:
                messages.append(current_message)
                current_message = paragraph
        
        # Добавляем последнее сообщение, если оно не пустое
        if current_message:
            messages.append(current_message)
        
        return messages
    
    # Простое разбиение на части равной длины
    return [text[i:i+max_length] for i in range(0, len(text), max_length)]

def format_multi_part_message(parts: List[str]) -> List[str]:
    """
    Форматирует многочастное сообщение, добавляя индикаторы частей.
    
    Args:
        parts: Список частей сообщения
        
    Returns:
        List[str]: Форматированные части с индикаторами
    """
    if not parts:
        return []
    
    # Если сообщение состоит из одной части, возвращаем как есть
    if len(parts) == 1:
        return parts
    
    # Добавляем индикаторы к каждой части
    formatted_parts = []
    total_parts = len(parts)
    
    for i, part in enumerate(parts):
        part_indicator = f"[{i+1}/{total_parts}] "
        formatted_parts.append(part_indicator + part)
    
    return formatted_parts

def send_long_message(text: str) -> List[str]:
    """
    Главная функция для отправки длинных сообщений в стиле Индианы.
    Просто разбивает на части и форматирует их.
    
    Args:
        text: Текст сообщения
        
    Returns:
        List[str]: Список готовых к отправке частей сообщения
    """
    parts = process_text(text)
    
    # Если сообщение короткое, возвращаем его как есть
    if len(parts) == 1:
        return parts
    
    # Форматируем многочастное сообщение
    return format_multi_part_message(parts)
