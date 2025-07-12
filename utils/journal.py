import os
import json
import asyncio
import time
from datetime import datetime
from typing import Dict, Any, List, Optional, Union

# Пути к журналам
LOG_PATH = "data/journal.json"
WILDERNESS_PATH = "data/wilderness.md"
ARCHIVE_PATH = "data/archives"
MAX_LOG_SIZE = 1000  # Максимальное количество записей в журнале
ROTATION_SIZE = 500  # Количество записей для архивации

def ensure_directories() -> None:
    """Создает необходимые директории, если они не существуют."""
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    os.makedirs(ARCHIVE_PATH, exist_ok=True)

def log_event(event: Dict[str, Any]) -> bool:
    """
    Добавляет событие (dict) с временной меткой в JSON-файл журнала.
    
    Args:
        event: Словарь с данными события
        
    Returns:
        bool: True если запись успешна, False если произошла ошибка
    """
    try:
        # Убеждаемся, что директории существуют
        ensure_directories()
        
        # Создаем файл, если он не существует
        if not os.path.isfile(LOG_PATH):
            with open(LOG_PATH, "w", encoding="utf-8") as f:
                f.write("[]")
        
        # Читаем существующие записи
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            try:
                log = json.load(f)
                if not isinstance(log, list):
                    log = []
            except json.JSONDecodeError:
                # Если файл поврежден, создаем новый журнал
                log = []
        
        # Добавляем новую запись с временной меткой
        log.append({
            "ts": datetime.now().isoformat(), 
            "unix_time": int(time.time()),
            **event
        })
        
        # Проверяем размер журнала и архивируем при необходимости
        if len(log) > MAX_LOG_SIZE:
            archive_logs(log[:-ROTATION_SIZE])
            log = log[-ROTATION_SIZE:]
        
        # Записываем обновленный журнал
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)
        
        return True
    except Exception as e:
        # Логируем ошибку в консоль, но не возбуждаем исключение
        print(f"Error writing to journal: {e}")
        return False

def wilderness_log(fragment: str) -> bool:
    """
    Добавляет текстовый фрагмент в журнал wilderness (файл Markdown).
    
    Args:
        fragment: Текстовый фрагмент для записи
        
    Returns:
        bool: True если запись успешна, False если произошла ошибка
    """
    try:
        ensure_directories()
        with open(WILDERNESS_PATH, "a", encoding="utf-8") as f:
            f.write(fragment.strip() + "\n\n")
        return True
    except Exception as e:
        print(f"Error writing to wilderness log: {e}")
        return False

def archive_logs(entries: List[Dict[str, Any]]) -> bool:
    """
    Архивирует старые записи журнала в отдельный файл.
    
    Args:
        entries: Список записей для архивации
        
    Returns:
        bool: True если архивация успешна, False если произошла ошибка
    """
    if not entries:
        return True
    
    try:
        # Создаем имя файла для архива на основе временной метки
        archive_name = f"journal_archive_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        archive_path = os.path.join(ARCHIVE_PATH, archive_name)
        
        # Записываем архив
        with open(archive_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
        
        return True
    except Exception as e:
        print(f"Error archiving logs: {e}")
        return False

def read_journal(limit: int = 100) -> List[Dict[str, Any]]:
    """
    Читает последние записи из журнала.
    
    Args:
        limit: Максимальное количество записей для чтения
        
    Returns:
        list: Список записей журнала
    """
    try:
        if not os.path.isfile(LOG_PATH):
            return []
        
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            try:
                log = json.load(f)
                if not isinstance(log, list):
                    return []
                return log[-limit:] if limit > 0 else log
            except json.JSONDecodeError:
                return []
    except Exception as e:
        print(f"Error reading journal: {e}")
        return []

def read_wilderness(limit_paragraphs: Optional[int] = None) -> str:
    """
    Читает содержимое журнала wilderness.
    
    Args:
        limit_paragraphs: Ограничение количества параграфов (None для чтения всего файла)
        
    Returns:
        str: Содержимое журнала wilderness
    """
    try:
        if not os.path.isfile(WILDERNESS_PATH):
            return ""
        
        with open(WILDERNESS_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        
        if limit_paragraphs:
            paragraphs = [p for p in content.split("\n\n") if p.strip()]
            content = "\n\n".join(paragraphs[-limit_paragraphs:])
        
        return content
    except Exception as e:
        print(f"Error reading wilderness log: {e}")
        return ""

async def log_event_async(event: Dict[str, Any]) -> bool:
    """
    Асинхронная версия log_event для использования в асинхронном коде.
    
    Args:
        event: Словарь с данными события
        
    Returns:
        bool: True если запись успешна, False если произошла ошибка
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, log_event, event)

async def wilderness_log_async(fragment: str) -> bool:
    """
    Асинхронная версия wilderness_log для использования в асинхронном коде.
    
    Args:
        fragment: Текстовый фрагмент для записи
        
    Returns:
        bool: True если запись успешна, False если произошла ошибка
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, wilderness_log, fragment)

def filter_logs(
    event_type: Optional[str] = None, 
    start_time: Optional[Union[str, datetime]] = None, 
    end_time: Optional[Union[str, datetime]] = None
) -> List[Dict[str, Any]]:
    """
    Фильтрует записи журнала по типу события и временному диапазону.
    
    Args:
        event_type: Тип события для фильтрации
        start_time: Начальное время для фильтрации (строка ISO или объект datetime)
        end_time: Конечное время для фильтрации (строка ISO или объект datetime)
        
    Returns:
        list: Список отфильтрованных записей
    """
    logs = read_journal(0)  # Читаем все записи
    filtered = []
    
    # Преобразуем даты в строки ISO, если они являются объектами datetime
    if isinstance(start_time, datetime):
        start_time = start_time.isoformat()
    if isinstance(end_time, datetime):
        end_time = end_time.isoformat()
    
    for entry in logs:
        # Фильтрация по типу
        if event_type and entry.get("type") != event_type:
            continue
            
        # Фильтрация по времени
        if start_time and entry.get("ts", "") < start_time:
            continue
        if end_time and entry.get("ts", "") > end_time:
            continue
            
        filtered.append(entry)
    
    return filtered
