import asyncio
import httpx
from typing import Optional, List
from loguru import logger
from app.core.config import get_settings

settings = get_settings()


class WhatsAppClient:
    def __init__(self):
        self.token = settings.WHATSAPP_ACCESS_TOKEN or ""
        self.phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID or ""
        self.base_url = f"https://graph.facebook.com/{settings.WHATSAPP_GRAPH_API_VERSION}"
        self._is_configured = bool(self.token and self.phone_number_id)
        logger.info(f"[WhatsApp] phone_number_id={self.phone_number_id or 'NO CONFIGURADO'}")
        logger.info(f"[WhatsApp] token={'OK (' + str(len(self.token)) + ' chars)' if self.token else 'NO CONFIGURADO'}")
        logger.info(f"[WhatsApp] is_configured={self._is_configured}")
    
    @property
    def is_configured(self) -> bool:
        return self._is_configured

    async def _post_message(self, payload: dict, label: str) -> dict:
        """POST a /messages payload with BSUID→phone fallback (Meta identity migration).

        We send BSUID-first (the durable identity), but Meta only enables OUTBOUND
        sending to a BSUID from ~June 2026 — until then the API rejects it with
        (#131009) "phone format". So if the primary send fails and the recipient
        wasn't already the session phone, we retry once with the phone from the
        current-turn identity ([app/core/identity.py]). This keeps delivery working
        today and switches to BSUID automatically once Meta enables it — no code change.
        """
        url = f"{self.base_url}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers)
            result = response.json()
            if response.status_code < 400:
                msg_id = result.get("messages", [{}])[0].get("id", "?")
                logger.info(f"[WhatsApp] ✅ {label} OK → {payload.get('to')} | message_id={msg_id}")
                return result

            # Primary send failed — try the session phone as fallback.
            to0 = payload.get("to")
            fallback_phone = None
            try:
                from app.core.identity import get_current_contact
                fallback_phone = (get_current_contact() or {}).get("phone")
            except Exception:
                fallback_phone = None

            if fallback_phone and fallback_phone != to0:
                err = (result.get("error") or {}).get("message", "")
                logger.warning(
                    f"[WhatsApp] {label} to {to0} failed ({response.status_code}: {err}); "
                    f"retrying via phone {fallback_phone}"
                )
                payload = {**payload, "to": fallback_phone}
                response = await client.post(url, json=payload, headers=headers)
                result = response.json()
                if response.status_code < 400:
                    msg_id = result.get("messages", [{}])[0].get("id", "?")
                    logger.info(f"[WhatsApp] ✅ {label} OK (phone fallback) → {fallback_phone} | message_id={msg_id}")
                    return result

            logger.error(f"[WhatsApp] ❌ {label} FAILED ({response.status_code}): {result}")
            return result

    async def send_message(self, to: str, message: str) -> dict:
        """Send a text message via WhatsApp."""
        if not self.is_configured:
            logger.warning("WhatsApp not configured - message not sent")
            return {"error": "WhatsApp not configured"}
        return await self._post_message(
            {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "text",
                "text": {"body": message},
            },
            "send_message",
        )

    async def send_image(self, to: str, image_url: str, caption: str = "") -> dict:
        """Send a single image via WhatsApp using image message type."""
        if not self.is_configured:
            logger.warning("WhatsApp not configured - image not sent")
            return {"error": "WhatsApp not configured"}
        return await self._post_message(
            {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "image",
                "image": {"link": image_url, "caption": caption or ""},
            },
            "send_image",
        )

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
    """Send up to 4 images via WhatsApp with rate-limiting delay (1s between sends)."""
    if not image_urls:
        return True
    try:
        for i, url in enumerate(image_urls[:4]):
            result = await whatsapp_client.send_image(to=phone, image_url=url, caption=caption)
            if result is None or (isinstance(result, dict) and result.get("error")):
                logger.warning(f"WhatsApp image send failed (index {i}): {result}")
            if i < len(image_urls[:4]) - 1:
                await asyncio.sleep(1.0)
        return True
    except Exception as e:
        logger.error(f"WhatsApp image send failed: {e}")
        return False
