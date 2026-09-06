import io
import json
import socket
import unittest
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

from reporting.google_sheets_gateway import GoogleSheetsGateway, SheetsGatewayError


class Response:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


def metadata(title="KPI Snapshots v2"):
    return {"sheets": [{"properties": {"sheetId": 1, "title": title}}]}


class GoogleSheetsGatewayTests(unittest.TestCase):
    def test_config_injection_reads_metadata_and_values(self):
        seen = []

        def opener(request, timeout):
            seen.append((request.full_url, request.get_header("Authorization"), timeout))
            return Response(metadata() if "?fields=" in request.full_url else {"values": [["header"]]})

        gateway = GoogleSheetsGateway(lambda: "runtime-token", opener=opener, api_root="https://example.test")
        self.assertEqual(gateway.read_values("book", "KPI Snapshots v2", "A1:A1"), [["header"]])
        self.assertEqual(seen[0][1], "Bearer runtime-token")
        self.assertTrue(seen[0][0].startswith("https://example.test/v4/spreadsheets/book"))
        self.assertEqual(parse_qs(urlsplit(seen[1][0]).query), {"valueRenderOption": ["UNFORMATTED_VALUE"]})

    def test_read_values_preserves_numeric_and_blank_semantics(self):
        seen = []

        def opener(request, timeout):
            seen.append(request.full_url)
            if "?fields=" in request.full_url:
                return Response(metadata())
            return Response({"values": [["header", 12, None, ""]]})

        gateway = GoogleSheetsGateway(lambda: "runtime-token", opener=opener, api_root="https://example.test")
        values = gateway.read_values("book", "KPI Snapshots v2", "A1:D1")
        self.assertEqual(values, [["header", 12, None, ""]])
        self.assertIsInstance(values[0][1], int)
        self.assertIsNone(values[0][2])
        self.assertEqual(parse_qs(urlsplit(seen[1]).query)["valueRenderOption"], ["UNFORMATTED_VALUE"])

    def test_auth_wrong_spreadsheet_and_wrong_tab_fail_closed(self):
        with self.assertRaisesRegex(SheetsGatewayError, "AUTH_FAILED"):
            GoogleSheetsGateway(lambda: "", opener=lambda *_args, **_kwargs: Response({})).get_sheet_metadata("book", "tab")

        def not_found(request, timeout):
            raise HTTPError(request.full_url, 404, "missing", {}, io.BytesIO(b'{"error":"missing"}'))

        with self.assertRaisesRegex(SheetsGatewayError, "SHEET_NOT_FOUND"):
            GoogleSheetsGateway(lambda: "token", opener=not_found).get_sheet_metadata("missing", "tab")

        with self.assertRaisesRegex(SheetsGatewayError, "TAB_NOT_FOUND"):
            GoogleSheetsGateway(lambda: "token", opener=lambda *_args, **_kwargs: Response(metadata("other tab"))).get_sheet_metadata("book", "tab")

    def test_sheets_401_and_403_are_auth_failures(self):
        for status in (401, 403):
            with self.subTest(status=status):
                def denied(request, timeout):
                    raise HTTPError(request.full_url, status, "denied", {}, io.BytesIO(b'{"error":"denied"}'))

                with self.assertRaisesRegex(SheetsGatewayError, "AUTH_FAILED"):
                    GoogleSheetsGateway(lambda: "token", opener=denied).get_sheet_metadata("book", "tab")

    def test_read_timeout_is_a_remote_read_failure(self):
        def timeout(request, timeout):
            raise URLError(socket.timeout("synthetic timeout"))

        with self.assertRaisesRegex(SheetsGatewayError, "REMOTE_READ_FAILED"):
            GoogleSheetsGateway(lambda: "token", opener=timeout).get_sheet_metadata("book", "tab")

    def test_malformed_read_and_write_failures_have_stable_codes(self):
        gateway = GoogleSheetsGateway(
            lambda: "token",
            opener=lambda request, timeout: Response(metadata() if "?fields=" in request.full_url else {"values": ["not-a-row"]}),
        )
        with self.assertRaisesRegex(SheetsGatewayError, "MALFORMED_REMOTE_ROW"):
            gateway.read_values("book", "KPI Snapshots v2", "A1:A1")

        def write_failure(request, timeout):
            if request.method == "POST":
                raise HTTPError(request.full_url, 500, "failure", {}, io.BytesIO(b'{"error":"failure"}'))
            return Response(metadata())

        with self.assertRaisesRegex(SheetsGatewayError, "REMOTE_WRITE_FAILED"):
            GoogleSheetsGateway(lambda: "token", opener=write_failure).batch_update("book", [{"appendCells": {}}])
        with self.assertRaisesRegex(SheetsGatewayError, "REMOTE_WRITE_FAILED"):
            GoogleSheetsGateway(lambda: "token", opener=write_failure).batch_update("book", [{"updateCells": {}}])

    def test_write_timeout_is_uncertain_not_retried_by_gateway(self):
        def timeout(request, timeout):
            raise URLError(socket.timeout("synthetic timeout"))

        with self.assertRaisesRegex(SheetsGatewayError, "WRITE_RESULT_UNCERTAIN"):
            GoogleSheetsGateway(lambda: "token", opener=timeout).batch_update("book", [{"appendCells": {}}])
