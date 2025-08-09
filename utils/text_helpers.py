import difflib
import httpx
import asyncio
from bs4 import BeautifulSoup
import re
import os
import ipaddress
import logging
from typing import List, Dict, Any, Optional, Union, Tuple
from urllib.parse import urlparse

# Настройки по умолчанию
DEFAULT_TIMEOUT = 15  # секунд
DEFAULT_MAX_TEXT_LENGTH = 5000  # символов

# Доменные списки
ALLOWED_DOMAINS = set(filter(None, os.getenv("ALLOWED_DOMAINS", "").split(",")))
DENIED_DOMAINS = set(filter(None, os.getenv("DENIED_DOMAINS", "").split(",")))

# Конфигурация логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("text_helpers")

def _domain_match(host: str, domain: str) -> bool:
    """Проверяет соответствие домена, включая поддомены."""
    return host == domain or host.endswith(f".{domain}")

def _is_private_ip(host: str) -> bool:
    """Определяет, является ли хост приватным IP."""
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback
    except ValueError:
        return False

def _is_url_allowed(url: str) -> Tuple[bool, str]:
    """Проверяет, разрешен ли URL для обработки."""
    parsed = urlparse(url)
    host = parsed.hostname or ""

    if _is_private_ip(host):
        return False, "приватный IP"

    if any(_domain_match(host, d) for d in DENIED_DOMAINS):
        return False, "домен запрещен"

    if ALLOWED_DOMAINS and not any(_domain_match(host, d) for d in ALLOWED_DOMAINS):
        return False, "домен не разрешен"

    return True, ""

def fuzzy_match(a: str, b: str) -> float:
    """
    Возвращает коэффициент сходства между двумя строками используя difflib.
    
    Args:
        a: Первая строка
        b: Вторая строка
        
    Returns:
        float: Коэффициент сходства от 0.0 до 1.0
    """
    # Нормализуем строки для лучшего сравнения
    a = a.lower().strip()
    b = b.lower().strip()
    return difflib.SequenceMatcher(None, a, b).ratio()

def extract_text_from_url(
    url: str, 
    max_length: int = DEFAULT_MAX_TEXT_LENGTH,
    timeout: int = DEFAULT_TIMEOUT,
    clean_formatting: bool = True
) -> str:
    """
    Извлекает читабельный текст из заданного URL.
    Удаляет скрипты, стили, заголовки, футеры, навигацию и боковые панели.
    
    Args:
        url: URL для извлечения текста
        max_length: Максимальная длина извлекаемого текста
        timeout: Тайм-аут запроса в секундах
        clean_formatting: Очищать ли форматирование и удалять лишние пробелы
        
    Returns:
        str: Извлеченный текст или сообщение об ошибке
    """
    try:
        # Проверяем схему URL
        parsed_url = urlparse(url)
        if not parsed_url.scheme:
            url = "https://" + url
        allowed, reason = _is_url_allowed(url)
        if not allowed:
            logger.warning(f"Blocked URL: {url} - {reason}")
            return f"[URL заблокирован: {reason}]"
        
        # Устанавливаем заголовки для запроса
        headers = {
            "User-Agent": "Mozilla/5.0 (Selesta Agent)",
            "Accept": "text/html,application/xhtml+xml,application/xml",
            "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
        }
        
        # Выполняем запрос синхронно
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            
            # Определяем кодировку
            content_type = resp.headers.get('Content-Type', '')
            if 'charset=' in content_type:
                encoding = content_type.split('charset=')[-1].strip()
            else:
                encoding = resp.apparent_encoding or 'utf-8'
            
            # Парсим HTML с учетом кодировки
            soup = BeautifulSoup(resp.content.decode(encoding, errors='replace'), "html.parser")
            
            # Удаляем ненужные элементы
            for s in soup(['script', 'style', 'header', 'footer', 'nav', 'aside', 'meta', 'form']):
                s.decompose()
            
            # Извлекаем текст
            if clean_formatting:
                text = soup.get_text(separator="\n")
                lines = [line.strip() for line in text.splitlines() if line.strip()]
                
                # Объединяем строки и удаляем избыточные пробелы
                result = "\n".join(lines)
                result = re.sub(r'\n{3,}', '\n\n', result)  # Заменяем 3+ переносов строк на 2
                result = re.sub(r' {2,}', ' ', result)  # Заменяем 2+ пробела на 1
            else:
                # Сохраняем некоторое форматирование
                for br in soup.find_all('br'):
                    br.replace_with('\n')
                for p in soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'div']):
                    p.append('\n')
                text = soup.get_text()
                result = re.sub(r'\n{3,}', '\n\n', text)
            
            # Ограничиваем длину результата
            if len(result) > max_length:
                result = result[:max_length] + f"\n[Текст обрезан. Полная длина: {len(result)} символов]"
                
            return result
    except httpx.HTTPStatusError as e:
        return f"[Ошибка HTTP: {e.response.status_code}]"
    except httpx.RequestError as e:
        return f"[Ошибка запроса: {str(e)}]"
    except Exception as e:
        return f"[Ошибка загрузки страницы: {str(e)}]"

async def extract_text_from_url_async(
    url: str, 
    max_length: int = DEFAULT_MAX_TEXT_LENGTH,
    timeout: int = DEFAULT_TIMEOUT
) -> str:
    """
    Асинхронная версия функции extract_text_from_url.
    
    Args:
        url: URL для извлечения текста
        max_length: Максимальная длина извлекаемого текста
        timeout: Тайм-аут запроса в секундах
        
    Returns:
        str: Извлеченный текст или сообщение об ошибке
    """
    try:
        # Проверяем схему URL
        parsed_url = urlparse(url)
        if not parsed_url.scheme:
            url = "https://" + url
        allowed, reason = _is_url_allowed(url)
        if not allowed:
            logger.warning(f"Blocked URL: {url} - {reason}")
            return f"[URL заблокирован: {reason}]"

        # Устанавливаем заголовки для запроса
        headers = {
            "User-Agent": "Mozilla/5.0 (Selesta Agent)",
            "Accept": "text/html,application/xhtml+xml,application/xml",
            "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
        }
        
        # Выполняем запрос асинхронно
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            
            # Определяем кодировку
            content_type = resp.headers.get('Content-Type', '')
            if 'charset=' in content_type:
                encoding = content_type.split('charset=')[-1].strip()
            else:
                encoding = resp.encoding or 'utf-8'
            
            # Парсим HTML
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # Удаляем ненужные элементы
            for s in soup(['script', 'style', 'header', 'footer', 'nav', 'aside', 'meta']):
                s.decompose()
            
            # Извлекаем текст
            text = soup.get_text(separator="\n")
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            result = "\n".join(lines)
            
            # Ограничиваем длину результата
            if len(result) > max_length:
                result = result[:max_length] + f"\n[Текст обрезан. Полная длина: {len(result)} символов]"
                
            return result
    except Exception as e:
        return f"[Ошибка загрузки страницы: {str(e)}]"

def summarize_text(text: str, max_length: int = 1000) -> str:
    """
    Простое сжатие текста без использования сторонних API.
    Выбирает наиболее важные предложения на основе частоты слов.
    
    Args:
        text: Исходный текст
        max_length: Максимальная длина суммаризации
        
    Returns:
        str: Сжатый текст
    """
    # Если текст короче максимальной длины, возвращаем как есть
    if len(text) <= max_length:
        return text
    
    # Разбиваем текст на предложения
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    # Если предложений мало, возвращаем первые несколько предложений
    if len(sentences) <= 3:
        return " ".join(sentences[:2])
    
    # Считаем частоту слов
    words = {}
    for sentence in sentences:
        for word in re.findall(r'\w+', sentence.lower()):
            if len(word) > 2:  # Игнорируем короткие слова
                words[word] = words.get(word, 0) + 1
    
    # Оцениваем предложения по частоте слов
    sentence_scores = []
    for i, sentence in enumerate(sentences):
        score = 0
        for word in re.findall(r'\w+', sentence.lower()):
            if len(word) > 2:
                score += words.get(word, 0)
        # Добавляем бонус первым и последним предложениям
        if i == 0 or i == len(sentences) - 1:
            score *= 1.5
        sentence_scores.append((i, score, sentence))
    
    # Сортируем предложения по оценке
    sorted_sentences = sorted(sentence_scores, key=lambda x: x[1], reverse=True)
    
    # Выбираем лучшие предложения и сортируем их по исходному порядку
    top_sentences = sorted_sentences[:min(5, len(sentences) // 2)]
    top_sentences = sorted(top_sentences, key=lambda x: x[0])
    
    # Составляем суммаризированный текст
    summary = " ".join(s[2] for s in top_sentences)
    
    # Если суммаризация все еще слишком длинная
    if len(summary) > max_length:
        summary = summary[:max_length-3] + "..."
    
    return summary

def clean_text(text: str, preserve_newlines: bool = True) -> str:
    """
    Очищает текст от лишних пробелов, HTML-тегов и другого мусора.
    
    Args:
        text: Исходный текст
        preserve_newlines: Сохранять ли переводы строк
        
    Returns:
        str: Очищенный текст
    """
    if not text:
        return ""
    
    # Удаляем HTML-теги
    text = re.sub(r'<[^>]+>', ' ', text)
    
    # Заменяем множественные пробелы на один
    text = re.sub(r' {2,}', ' ', text)
    
    # Обрабатываем переводы строк
    if preserve_newlines:
        # Заменяем множественные переводы строк на двойные
        text = re.sub(r'\n{3,}', '\n\n', text)
    else:
        # Заменяем все переводы строк на пробелы
        text = re.sub(r'\s*\n\s*', ' ', text)
    
    # Удаляем пробелы в начале и конце строк
    text = text.strip()
    
    return text

def extract_urls(text: str) -> List[str]:
    """
    Извлекает все URL из текста.
    
    Args:
        text: Исходный текст
        
    Returns:
        List[str]: Список найденных URL
    """
    # Регулярное выражение для поиска URL
    url_pattern = r'https?://[^\s<>"]+|www\.[^\s<>"]+|[^\s<>"]+\.[a-z]{2,}(?=/[^\s<>"]*)'
    
    # Находим все URL
    urls = re.findall(url_pattern, text)
    
    # Фильтруем и нормализуем URL
    valid_urls = []
    for url in urls:
        # Добавляем протокол, если его нет
        if url.startswith('www.'):
            url = 'https://' + url
        
        # Проверяем, что URL имеет допустимый формат
        try:
            parsed = urlparse(url)
            if parsed.netloc and '.' in parsed.netloc:
                valid_urls.append(url)
        except Exception:
            continue
    
    return valid_urls

def truncate_text(text: str, max_length: int = 100, add_ellipsis: bool = True) -> str:
    """
    Обрезает текст до указанной длины, сохраняя целостность слов.
    
    Args:
        text: Исходный текст
        max_length: Максимальная длина результата
        add_ellipsis: Добавлять ли многоточие в конце обрезанного текста
        
    Returns:
        str: Обрезанный текст
    """
    if not text:
        return ""
    
    if len(text) <= max_length:
        return text
    
    # Обрезаем текст до max_length символов
    truncated = text[:max_length]
    
    # Находим последнее полное слово
    last_space = truncated.rfind(' ')
    if last_space > max_length * 0.8:  # Если последний пробел достаточно близко к концу
        truncated = truncated[:last_space]
    
    # Добавляем многоточие, если требуется
    if add_ellipsis:
        truncated += "..."
    
    return truncated
