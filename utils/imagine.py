import openai
import os

def generate_image(prompt, chat_id=None, model="dall-e-3", size="1024x1024"):
    """
    Generates an image using OpenAI DALL-E (3 or 2) and returns the image URL.
    Falls back to DALL-E 2 if DALL-E 3 is not available.
    Returns an English error message if generation fails.
    """
    openai.api_key = os.getenv("OPENAI_API_KEY")
    try:
        response = openai.images.generate(
            model=model,
            prompt=prompt,
            n=1,
            size=size
        )
        # Support both OpenAI v1 and v2 response structures
        if hasattr(response, "data") and response.data and hasattr(response.data[0], "url"):
            return response.data[0].url
        elif isinstance(response, dict) and "data" in response and response["data"]:
            return response["data"][0]["url"]
        else:
            return "[Image generation error: No image URL in response.]"
    except Exception as e:
        # Fallback: try DALL-E 2 if DALL-E 3 fails
        if model == "dall-e-3":
            try:
                response = openai.images.generate(
                    model="dall-e-2",
                    prompt=prompt,
                    n=1,
                    size=size
                )
                if hasattr(response, "data") and response.data and hasattr(response.data[0], "url"):
                    return response.data[0].url
                elif isinstance(response, dict) and "data" in response and response["data"]:
                    return response["data"][0]["url"]
                else:
                    return "[Image generation error: No image URL in response (fallback).]"
            except Exception as e2:
                return f"[Image generation error (fallback): {str(e2)}]"
        return f"[Image generation error: {str(e)}]"
