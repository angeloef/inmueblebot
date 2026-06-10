"""Plan #6: verify Meta's x-hub-signature-256 over the raw request body.

Without this, anyone who knows the webhook URL can forge user turns. The endpoint
now fail-closes when WHATSAPP_APP_SECRET is configured: a missing or invalid
signature → 403; a valid signature → processed.

Offline: exercises verify_webhook_signature directly, plus the endpoint's 403 path
with a stub Request (no network / Meta).
"""

import asyncio
import hashlib
import hmac
import json
import unittest

from fastapi import HTTPException

from app.api.routes import webhook as wh

_SECRET = "test-app-secret"


def _sign(raw: bytes, secret: str = _SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


class _StubRequest:
    """Minimal stand-in for fastapi.Request exposing body() + headers."""

    def __init__(self, raw: bytes, headers: dict):
        self._raw = raw
        self.headers = headers

    async def body(self) -> bytes:
        return self._raw


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class TestVerifyWebhookSignature(unittest.TestCase):

    def test_valid_signature_accepted(self):
        raw = b'{"object":"whatsapp_business_account"}'
        self.assertTrue(wh.verify_webhook_signature(raw, _sign(raw), _SECRET))

    def test_tampered_body_rejected(self):
        raw = b'{"object":"whatsapp_business_account"}'
        sig = _sign(raw)
        self.assertFalse(wh.verify_webhook_signature(b'{"object":"forged"}', sig, _SECRET))

    def test_missing_header_rejected(self):
        raw = b'{"x":1}'
        self.assertFalse(wh.verify_webhook_signature(raw, "", _SECRET))

    def test_malformed_header_rejected(self):
        raw = b'{"x":1}'
        self.assertFalse(wh.verify_webhook_signature(raw, "deadbeef", _SECRET))

    def test_wrong_secret_rejected(self):
        raw = b'{"x":1}'
        self.assertFalse(wh.verify_webhook_signature(raw, _sign(raw, "other"), _SECRET))


class TestEndpointEnforcesSignature(unittest.TestCase):
    """The POST endpoint returns 403 on a forged request when the secret is set."""

    def setUp(self):
        self._orig = wh.get_settings

    def tearDown(self):
        wh.get_settings = self._orig

    def _patch_secret(self, secret):
        class _S:
            WHATSAPP_APP_SECRET = secret
        wh.get_settings = lambda: _S()

    def test_forged_payload_returns_403(self):
        self._patch_secret(_SECRET)
        req = _StubRequest(b'{"object":"forged"}', {"x-hub-signature-256": "sha256=bad"})
        with self.assertRaises(HTTPException) as ctx:
            _run(wh.receive_webhook(req))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_missing_signature_returns_403(self):
        self._patch_secret(_SECRET)
        req = _StubRequest(b'{"object":"x"}', {})
        with self.assertRaises(HTTPException) as ctx:
            _run(wh.receive_webhook(req))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_no_secret_configured_skips_verification(self):
        """Legacy behaviour: with no app secret, an unsigned request is not rejected."""
        self._patch_secret(None)
        raw = json.dumps({"object": "whatsapp_business_account", "entry": []}).encode()
        req = _StubRequest(raw, {})
        result = _run(wh.receive_webhook(req))
        # Returns the normal ok envelope, not a 403.
        self.assertEqual(result.get("status"), "ok")


if __name__ == "__main__":
    unittest.main()
