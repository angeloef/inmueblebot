import httpx
from typing import Optional, List
from loguru import logger
from app.core.config import get_settings

settings = get_settings()


class WhatsAppClient:
    def __init__(self):
        self.token = settings.WHATSAPP_ACCESS_TOKEN or ""
        self.phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID or ""
        self.base_url = "https://graph.facebook.com/v18.0"
        self._is_configured = bool(self.token and self.phone_number_id)
        logger.info(f"[WhatsApp] phone_number_id={self.phone_number_id or 'NO CONFIGURADO'}")
        logger.info(f"[WhatsApp] token={'OK (' + str(len(self.token)) + ' chars)' if self.token else 'NO CONFIGURADO'}")
        logger.info(f"[WhatsApp] is_configured={self._is_configured}")
    
    @property
    def is_configured(self) -> bool:
        return self._is_configured
    
    async def send_message(self, to: str, message: str) -> dict:
        """Send a text message via WhatsApp."""
        if not self.is_configured:
            logger.warning("WhatsApp not configured - message not sent")
            return {"error": "WhatsApp not configured"}
        
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
            result = response.json()
            if response.status_code >= 400:
                logger.error(f"[WhatsApp] ❌ send_message FAILED ({response.status_code}): {result}")
            else:
                msg_id = result.get("messages", [{}])[0].get("id", "?")
                logger.info(f"[WhatsApp] ✅ send_message OK → {to} | message_id={msg_id}")
            return result

    async def send_image(self, to: str, image_url: str, caption: str = "") -> dict:
        """Send a single image via WhatsApp using image message type."""
        if not self.is_configured:
            logger.warning("WhatsApp not configured - image not sent")
            return {"error": "WhatsApp not configured"}
        
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

    async def send_interactive_buttons(self, to: str, body_text: str, buttons: List[dict]) -> dict:
        """Send interactive buttons message."""
        if not self.is_configured:
            logger.warning("WhatsApp not configured - buttons not sent")
            return {"error": "WhatsApp not configured"}
        
        url = f"{self.base_url}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body_text},
                "action": {"buttons": buttons}
            }
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers)
            return response.json()

    async def send_template(self, to: str, template_name: str, components: Optional[list] = None) -> dict:
        """Send a template message."""
        if not self.is_configured:
            logger.warning("WhatsApp not configured - template not sent")
            return {"error": "WhatsApp not configured"}
        
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


async def send_whatsapp_message(phone: str, message: str) -> bool:
    """Send a text message. Returns True if successful."""
    try:
        result = await whatsapp_client.send_message(to=phone, message=message)
        return "error" not in result
    except Exception as e:
        logger.error(f"WhatsApp send failed: {e}")
        return False


async def send_whatsapp_images(phone: str, image_urls: List[str], caption: str = "") -> bool:
    """Send up to 3 images via WhatsApp."""
    if not image_urls:
        return True
    try:
        for url in image_urls[:3]:
            await whatsapp_client.send_image(to=phone, image_url=url, caption=caption)
        return True
    except Exception as e:
        logger.error(f"WhatsApp image send failed: {e}")
        return False
