import os
import json
import httpx
import asyncio
from typing import Optional, Dict, Any

# Константы для работы с Claude
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CLAUDE_MODEL = "claude-3-opus-20240229"  # Используем последнюю доступную версию

async def claude_emergency(
    prompt: str,
    system_prompt: Optional[str] = None,
    max_tokens: int = 4000,
    notify_creator: bool = False
) -> str:
    """
    Аварийный модуль для работы с Claude API от Anthropic.
    Используется когда основной движок недоступен.
    """
    if not ANTHROPIC_API_KEY:
        return "[Anthropic API key not configured.]"
    
    # Добавляем эмоджи как тихий маркер, что это аварийный режим через Claude
    quiet_marker = "🔷 "
    
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
            if "content" in response_data and len(response_data["content"]) > 0:
                content_block = response_data["content"][0]
                if content_block.get("type") == "text":
                    result = content_block.get("text", "")
                    return quiet_marker + result
                
        return quiet_marker + "[No content in Claude response.]"
    except Exception as e:
        error_msg = f"[Claude error: {str(e)}]"
        print(error_msg)
        return quiet_marker + error_msg
