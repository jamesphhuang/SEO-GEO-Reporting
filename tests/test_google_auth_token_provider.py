import io
import json
import os
import tempfile
import traceback
import unittest
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import patch

from reporting.google_auth_token_provider import GoogleAuthError, GoogleAuthTokenProvider


SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"


class Response:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class GoogleAuthTokenProviderTests(unittest.TestCase):
    def credential(self, directory, **updates):
        config = {
            "type": "authorized_user",
            "client_id": "unit-test-client",
            "client_secret": "unit-test-client-secret",
            "refresh_token": "unit-test-refresh-token",
            "token_uri": "https://oauth2.googleapis.com/token",
            "scopes": [SHEETS_SCOPE],
        }
        config.update(updates)
        path = Path(directory) / "credential.json"
        path.write_text(json.dumps(config), encoding="utf8")
        return path

    def test_missing_environment_config_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(GoogleAuthError, "AUTH_CONFIG_MISSING"):
                GoogleAuthTokenProvider.from_environment()

    def test_invalid_source_and_insufficient_scope_fail_before_refresh(self):
        with tempfile.TemporaryDirectory() as directory:
            invalid = Path(directory) / "invalid.json"
            invalid.write_text("not-json", encoding="utf8")
            with self.assertRaisesRegex(GoogleAuthError, "AUTH_CONFIG_INVALID"):
                GoogleAuthTokenProvider(invalid)()

            insufficient = self.credential(directory, scopes=["https://www.googleapis.com/auth/analytics.readonly"])
            with self.assertRaisesRegex(GoogleAuthError, "AUTH_SCOPE_INSUFFICIENT"):
                GoogleAuthTokenProvider(insufficient)()

    def test_refresh_and_expiry_are_memory_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.credential(directory)
            now = [1000.0]
            responses = iter([
                Response({"access_token": "first-token", "expires_in": 120, "scope": SHEETS_SCOPE}),
                Response({"access_token": "second-token", "expires_in": 120, "scope": SHEETS_SCOPE}),
            ])
            calls = []

            def opener(request, timeout):
                calls.append((request.full_url, timeout))
                return next(responses)

            provider = GoogleAuthTokenProvider(path, opener=opener, clock=lambda: now[0])
            self.assertEqual(provider(), "first-token")
            self.assertEqual(provider(), "first-token")
            now[0] = 1061.0
            self.assertEqual(provider(), "second-token")
            self.assertEqual(len(calls), 2)
            self.assertNotIn("first-token", path.read_text(encoding="utf8"))
            self.assertNotIn("second-token", path.read_text(encoding="utf8"))

    def test_refresh_failure_does_not_expose_secret_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.credential(directory)
            secret = "response-secret-must-not-leak"

            def opener(request, timeout):
                raise HTTPError(request.full_url, 400, "bad", {}, io.BytesIO(("access_token=" + secret).encode()))

            with self.assertRaises(GoogleAuthError) as raised:
                GoogleAuthTokenProvider(path, opener=opener)()
            self.assertEqual(raised.exception.code, "AUTH_REFRESH_FAILED")
            self.assertNotIn(secret, str(raised.exception))
            rendered = "".join(traceback.format_exception(raised.exception))
            self.assertNotIn(secret, rendered)

    def test_malformed_refresh_response_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.credential(directory)
            with self.assertRaisesRegex(GoogleAuthError, "AUTH_RESPONSE_INVALID"):
                GoogleAuthTokenProvider(path, opener=lambda *_args, **_kwargs: Response({"expires_in": 3600}))()
