import os
import httpx
import asyncio
from typing import Optional

# Поддерживаемые модели и размеры
DALL_E_3_MODELS = ["dall-e-3"]
DALL_E_2_MODELS = ["dall-e-2"]
SUPPORTED_MODELS = DALL_E_3_MODELS + DALL_E_2_MODELS

# Поддерживаемые размеры изображений для каждой модели
SIZE_MAP = {
    "dall-e-3": ["1024x1024", "1792x1024", "1024x1792"],
    "dall-e-2": ["256x256", "512x512", "1024x1024"]
}

# Максимальное количество попыток генерации
MAX_RETRIES = 3
RETRY_DELAY = 2  # секунды между попытками

# Эмоджи для разных типов картинок
IMAGE_EMOJI = {
    "landscape": "🌄",
    "portrait": "🖼️",
    "square": "🎨",
    "error": "⚠️",
    "default": "🎭"
}

def get_image_emoji(size: str) -> str:
    """Возвращает соответствующий эмоджи в зависимости от размера изображения."""
    if size == "1024x1024":
        return IMAGE_EMOJI["square"]
    elif "1792x1024" in size:
        return IMAGE_EMOJI["landscape"]
    elif "1024x1792" in size:
        return IMAGE_EMOJI["portrait"]
    return IMAGE_EMOJI["default"]

def enhance_prompt(prompt: str) -> str:
    """
    Улучшает промпт для генерации изображений, добавляя детали 
    и элементы стиля, если они не указаны.
    """
    # Если промпт слишком короткий, добавляем детали качества
    if len(prompt) < 10:
        return f"{prompt}, high quality, detailed"
    
    # Если в промпте не указано качество, добавляем его
    quality_terms = ["high quality", "detailed", "high resolution", "4k", "8k"]
    if not any(term in prompt.lower() for term in quality_terms):
        return f"{prompt}, high quality"
    
    return prompt

__all__ = ["generate_image_async"]

async def generate_image_async(
    prompt: str,
    chat_id: Optional[str] = None,
    model: str = "dall-e-3",
    size: str = "1024x1024",
    api_key: Optional[str] = None
) -> str:
    """
    Асинхронно генерирует изображение с использованием OpenAI API.
    
    Args:
        prompt: Текстовый запрос для генерации
        chat_id: ID чата (для логирования)
        model: Модель для генерации (dall-e-3 или dall-e-2)
        size: Размер генерируемого изображения
        api_key: Ключ API OpenAI (если не указан, берется из переменных окружения)
    
    Returns:
        URL сгенерированного изображения или сообщение об ошибке
    """
    # Получаем API ключ
    api_key = api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        return f"{IMAGE_EMOJI['error']} [Image generation error: API key not found.]"
    
    # Проверяем модель
    if model not in SUPPORTED_MODELS:
        model = "dall-e-3"  # Используем dall-e-3 по умолчанию
    
    # Проверяем размер
    if size not in SIZE_MAP.get(model, ["1024x1024"]):
        size = "1024x1024"  # Используем 1024x1024 по умолчанию
    
    # Улучшаем промпт
    enhanced_prompt = enhance_prompt(prompt)
    
    # Добавляем эмоджи к результату в зависимости от размера
    emoji = get_image_emoji(size)
    
    # Формируем данные для запроса
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": model,
        "prompt": enhanced_prompt,
        "n": 1,
        "size": size
    }
    
    # Пробуем генерировать изображение с повторными попытками
    for attempt in range(MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    "https://api.openai.com/v1/images/generations",
                    headers=headers,
                    json=data
                )
                response.raise_for_status()
                response_data = response.json()
                
                # Извлекаем URL изображения
                if "data" in response_data and response_data["data"]:
                    url = response_data["data"][0].get("url", "")
                    if url:
                        return f"{emoji} {url}"
                
                # Если URL не найден
                return f"{IMAGE_EMOJI['error']} [Image generation error: No image URL in response.]"
            
        except httpx.HTTPStatusError as e:
            if attempt < MAX_RETRIES - 1:
                # Если это не последняя попытка, ждем и пробуем снова
                await asyncio.sleep(RETRY_DELAY)
            else:
                # Если это DALL-E 3 и последняя попытка, пробуем DALL-E 2
                if model in DALL_E_3_MODELS:
                    try:
                        data["model"] = "dall-e-2"
                        # Убеждаемся, что размер подходит для DALL-E 2
                        if size not in SIZE_MAP["dall-e-2"]:
                            data["size"] = "1024x1024"
                            
                        async with httpx.AsyncClient(timeout=60.0) as client:
                            response = await client.post(
                                "https://api.openai.com/v1/images/generations",
                                headers=headers,
                                json=data
                            )
                            response.raise_for_status()
                            response_data = response.json()
                            
                            if "data" in response_data and response_data["data"]:
                                url = response_data["data"][0].get("url", "")
                                if url:
                                    return f"{emoji} {url} (DALL-E 2 fallback)"
                    except Exception as e2:
                        return f"{IMAGE_EMOJI['error']} [DALL-E fallback error: {str(e2)}]"
                
                return f"{IMAGE_EMOJI['error']} [Image generation error: {str(e)}]"
        
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY)
            else:
                return f"{IMAGE_EMOJI['error']} [Image generation error: {str(e)}]"
    
    return f"{IMAGE_EMOJI['error']} [Image generation failed after {MAX_RETRIES} attempts.]"
