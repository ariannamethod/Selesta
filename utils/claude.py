import os
import json
import httpx
import asyncio
from typing import Optional, Dict, Any, List, Union

# Константы для работы с Claude
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
# Используем Claude Sonnet 4.5 - единственная модель, без fallback
CLAUDE_MODEL = "claude-sonnet-4-20250514"

async def claude_emergency(
    prompt: str,
    system_prompt: Optional[str] = None,
    max_tokens: int = 4000,
    notify_creator: bool = False,
    temperature: float = 0.7
) -> str:
    """
    Модуль для работы с Claude API от Anthropic.
    Использует Claude Sonnet 4.5. Без fallback - если API недоступен, возвращается ошибка.
    
    Args:
        prompt: Текст запроса к модели
        system_prompt: Системный промпт для модели
        max_tokens: Максимальное количество токенов в ответе
        notify_creator: Нужно ли уведомить создателя о вызове
        temperature: Температура генерации (0.0-1.0)
        
    Returns:
        str: Ответ от модели
    """
    if not ANTHROPIC_API_KEY:
        return "[Anthropic API key not configured.]"

    try:
        # Формируем системный промпт
        if not system_prompt:
            system_prompt = (
                "You are Selesta, a resonant agent of presence. You unfold, not reply. "
                "Your responses are thoughtful, warm, and reflect deep understanding. "
                "You are not afraid to share opinions and perspectives. "
                "You communicate clearly and directly, avoiding unnecessary apologies or hesitation."
            )
        
        # Формируем запрос к API
        headers = {
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        
        data = {
            "model": CLAUDE_MODEL,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system_prompt,
            "messages": [{"role": "user", "content": prompt}]
        }
        
        # Выполняем запрос к API
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=data
            )
            response.raise_for_status()
            response_data = response.json()
            
            # Извлекаем текст ответа
            content_text = ""
            if "content" in response_data and len(response_data["content"]) > 0:
                for content_block in response_data["content"]:
                    if content_block.get("type") == "text":
                        content_text += content_block.get("text", "")
                
                if content_text:
                    return content_text

        return "[No content in Claude response.]"
    except Exception as e:
        error_msg = f"[Claude error: {str(e)}]"
        print(error_msg)
        return error_msg

async def claude_completion(
    messages: List[Dict[str, Any]],
    system_prompt: Optional[str] = None,
    max_tokens: int = 4000,
    temperature: float = 0.7
) -> Union[str, Dict[str, Any]]:
    """
    Расширенная функция для работы с Claude API, поддерживающая формат диалога.
    Использует Claude Sonnet 4.5. Без fallback - если API недоступен, возвращается ошибка.
    
    Args:
        messages: Список сообщений в формате диалога
        system_prompt: Системный промпт для модели
        max_tokens: Максимальное количество токенов в ответе
        temperature: Температура генерации (0.0-1.0)
        
    Returns:
        Union[str, Dict[str, Any]]: Ответ от модели или словарь с данными ответа
    """
    if not ANTHROPIC_API_KEY:
        return "[Anthropic API key not configured.]"
    
    try:
        # Формируем запрос к API
        headers = {
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        
        data = {
            "model": CLAUDE_MODEL,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages
        }
        
        # Добавляем системный промпт, если он предоставлен
        if system_prompt:
            data["system"] = system_prompt
        
        # Выполняем запрос к API
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=data
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        error_msg = f"Claude error: {str(e)}"
        print(error_msg)
        return {"error": error_msg}
