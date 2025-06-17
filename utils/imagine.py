import openai
import os

def generate_image(prompt, chat_id=None, model="dall-e-3", size="1024x1024"):
    """
    Generates an image using OpenAI DALL-E and returns the image URL.
    """
    openai.api_key = os.getenv("OPENAI_API_KEY")
    try:
        response = openai.images.generate(
            model=model,
            prompt=prompt,
            n=1,
            size=size
        )
        image_url = response.data[0].url
        return image_url
    except Exception as e:
        return f"Image generation error: {str(e)}"
