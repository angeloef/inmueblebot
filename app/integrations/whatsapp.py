import httpx
from typing import Optional, List
import logging
from config.settings import get_settings

settings = get_settings()


class WhatsAppClient:
    def __init__(self):
        self.token = settings.META_TOKEN
        self.phone_number_id = settings.META_PHONE_NUMBER_ID
        self.base_url = "https://graph.facebook.com/v18.0"

    async def send_message(self, to: str, message: str) -> dict:
        url = f"{self.base_url}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": message}
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers)
            return response.json()

    async def send_image(self, to: str, image_url: str, caption: str = "") -> dict:
        """Send a single image via WhatsApp using image message type."""
        url = f"{self.base_url}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "image",
            "image": {
                "link": image_url,
                "caption": caption or ""
            }
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers)
            return response.json()

    async def send_template(self, to: str, template_name: str, components: Optional[list] = None) -> dict:
        url = f"{self.base_url}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": "es_MX"},
                "components": components or []
            }
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers)
            return response.json()


whatsapp_client = WhatsAppClient()


async def send_whatsapp_images(phone: str, image_urls: List[str], caption: str = "") -> bool:
    """Placeholder: send up to 3 images via WhatsApp. Uses send_image under the hood."""
    if not image_urls:
        return True
    try:
        # Send up to 3 images to avoid spam
        for idx, url in enumerate(image_urls[:3]):
            await whatsapp_client.send_image(to=phone, image_url=url, caption=caption)
        return True
    except Exception as e:
        logging.getLogger(__name__).error(f"WhatsApp image send failed: {e}")
        return False
