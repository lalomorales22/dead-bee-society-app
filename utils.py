import os
import requests
import logging
import base64

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def generate_dead_bee_image(prompt):
    logger.debug(f"Generating dead bee image with prompt: {prompt}")
    api_key = os.getenv("STABILITY_API_KEY")
    logger.debug(f"API Key: {api_key[:5]}...{api_key[-5:]} (length: {len(api_key)})")
    if not api_key:
        logger.error("Stability API key not set")
        return None, "Stability API key not set"

    url = "https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/text-to-image"
    logger.debug(f"API Endpoint: {url}")
    
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    # Modify the prompt to always include a bee
    bee_prompt = f"A detailed illustration of a bee in the following scene or context: {prompt}. The bee should be the main focus of the image."
    
    payload = {
        "text_prompts": [{"text": bee_prompt}],
        "cfg_scale": 7,
        "height": 1024,
        "width": 1024,
        "samples": 1,
        "steps": 30,
    }
    logger.debug(f"API Request Payload: {payload}")

    try:
        # Test API connectivity
        try:
            test_response = requests.get("https://api.stability.ai/v1/engines/list", headers=headers)
            logger.debug(f"API Connectivity Test: {test_response.status_code}")
            if test_response.status_code == 401:
                logger.error("API Key is invalid or expired")
                return None, "API Key is invalid or expired"
        except requests.exceptions.RequestException as e:
            logger.error(f"API Connectivity Test Failed: {str(e)}")

        logger.debug("Sending request to Stability AI API")
        response = requests.post(url, headers=headers, json=payload)
        logger.debug(f"API Response Status: {response.status_code}")
        logger.debug(f"API Response Headers: {response.headers}")
        logger.debug(f"API Response Content: {response.text[:1000]}...")  # Log first 1000 characters

        response.raise_for_status()
        data = response.json()
        logger.debug(f"API Response JSON: {data}")

        image_data = data["artifacts"][0]["base64"]
        logger.debug(f"Successfully generated image. Image data length: {len(image_data)}")
        return image_data, None
    except requests.exceptions.RequestException as e:
        logger.error(f"API Request Exception: {str(e)}")
        logger.error(f"API Error Response: {e.response.text if e.response else 'No response'}")
        return None, f"API error: {str(e)}"
    except KeyError as e:
        logger.error(f"KeyError while parsing API response: {str(e)}")
        return None, f"Error parsing API response: {str(e)}"
    except Exception as e:
        logger.error(f"Unexpected error in generate_dead_bee_image: {str(e)}")
        return None, f"Unexpected error: {str(e)}"
