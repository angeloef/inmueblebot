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
        """POST a /messages payload, phone-first with BSUID as opportunistic fallback.

        Meta only enables OUTBOUND sending to a BSUID from ~mid-2026 — until then the
        API rejects BSUID recipients with (#131009) "phone format". So we send to the
        session PHONE first (the path that works today) and only fall back to the
        originally-requested recipient (typically the BSUID) if no phone is known or
        the phone send fails. Once Meta enables BSUID outbound, the BSUID send will
        simply start succeeding — flip the order back then. See [app/core/identity.py].
        """
        url = f"{self.base_url}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

        requested_to = payload.get("to")
        session_phone = None
        try:
            from app.core.identity import get_current_contact
            session_phone = (get_current_contact() or {}).get("phone")
        except Exception:
            session_phone = None

        # Build the ordered list of recipients to try: phone first, then the original
        # (BSUID) target — de-duplicated, skipping falsy values.
        targets: list[str] = []
        for t in (session_phone, requested_to):
            if t and t not in targets:
                targets.append(t)

        async with httpx.AsyncClient() as client:
            result: dict = {}
            for idx, to in enumerate(targets):
                attempt_payload = {**payload, "to": to}
                response = await client.post(url, json=attempt_payload, headers=headers)
                result = response.json()
                if response.status_code < 400:
                    msg_id = result.get("messages", [{}])[0].get("id", "?")
                    suffix = "" if idx == 0 else " (fallback)"
                    logger.info(f"[WhatsApp] ✅ {label} OK{suffix} → {to} | message_id={msg_id}")
                    return result
                err = (result.get("error") or {}).get("message", "")
                # Only warn (and continue) if there's another target to try.
                if idx < len(targets) - 1:
                    logger.warning(
                        f"[WhatsApp] {label} to {to} failed ({response.status_code}: {err}); "
                        f"retrying via {targets[idx + 1]}"
                    )

            logger.error(f"[WhatsApp] ❌ {label} FAILED: {result}")
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
