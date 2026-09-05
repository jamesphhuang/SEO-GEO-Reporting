"""Minimal Google Sheets HTTP gateway with externally supplied credentials."""

import json
import socket
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class SheetsGatewayError(RuntimeError):
    """A fail-closed Google Sheets transport error with a stable machine code."""

    def __init__(self, code: str, detail: str):
        super().__init__(code + ": " + detail)
        self.code = code


class GoogleSheetsGateway:
    """Google Sheets v4 transport; callers inject a short-lived bearer-token provider."""

    def __init__(
        self,
        bearer_token_provider: Callable[[], str],
        *,
        opener: Callable[..., Any] = urlopen,
        timeout_seconds: float = 20,
        api_root: str = "https://sheets.googleapis.com",
    ):
        if not callable(bearer_token_provider):
            raise ValueError("bearer_token_provider must be callable")
        if type(timeout_seconds) not in (int, float) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.bearer_token_provider = bearer_token_provider
        self.opener = opener
        self.timeout_seconds = timeout_seconds
        self.api_root = api_root.rstrip("/")

    def _token(self) -> str:
        try:
            token = self.bearer_token_provider()
        except Exception as error:
            raise SheetsGatewayError("AUTH_FAILED", "credential provider failed") from error
        if not isinstance(token, str) or not token.strip():
            raise SheetsGatewayError("AUTH_FAILED", "credential provider returned no bearer token")
        return token

    def _request(self, method: str, path: str, *, payload: dict[str, Any] | None = None, write: bool = False) -> dict[str, Any]:
        body = json.dumps(payload, separators=(",", ":")).encode() if payload is not None else None
        request = Request(
            self.api_root + path,
            data=body,
            method=method,
            headers={"Authorization": "Bearer " + self._token(), "Content-Type": "application/json"},
        )
        try:
            with self.opener(request, timeout=self.timeout_seconds) as response:
                raw = response.read()
        except HTTPError as error:
            try:
                detail = error.read().decode(errors="replace")
            except Exception:
                detail = error.reason or "HTTP error"
            if error.code in (401, 403):
                code = "AUTH_FAILED"
            elif error.code == 404:
                code = "SHEET_NOT_FOUND"
            elif error.code == 400 and "range" in str(detail).lower():
                code = "TAB_NOT_FOUND"
            else:
                code = "REMOTE_WRITE_FAILED" if write else "REMOTE_READ_FAILED"
            raise SheetsGatewayError(code, str(detail)) from error
        except (TimeoutError, socket.timeout, URLError) as error:
            if write:
                raise SheetsGatewayError("WRITE_RESULT_UNCERTAIN", "transport failed after write dispatch") from error
            raise SheetsGatewayError("REMOTE_READ_FAILED", "transport failed before a readable response") from error
        try:
            decoded = json.loads(raw.decode())
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SheetsGatewayError("REMOTE_WRITE_FAILED" if write else "MALFORMED_REMOTE_ROW", "invalid JSON response") from error
        if not isinstance(decoded, dict):
            raise SheetsGatewayError("REMOTE_WRITE_FAILED" if write else "MALFORMED_REMOTE_ROW", "response is not an object")
        return decoded

    def get_sheet_metadata(self, spreadsheet_id: str, sheet_title: str) -> dict[str, Any]:
        if not isinstance(spreadsheet_id, str) or not spreadsheet_id or not isinstance(sheet_title, str) or not sheet_title:
            raise SheetsGatewayError("SHEET_NOT_FOUND", "spreadsheet id and tab title are required")
        metadata = self._request(
            "GET",
            "/v4/spreadsheets/" + quote(spreadsheet_id, safe="") + "?fields=sheets.properties",
        )
        sheets = metadata.get("sheets")
        if not isinstance(sheets, list):
            raise SheetsGatewayError("MALFORMED_REMOTE_ROW", "metadata has no sheets list")
        for sheet in sheets:
            properties = sheet.get("properties") if isinstance(sheet, dict) else None
            if isinstance(properties, dict) and properties.get("title") == sheet_title:
                return properties
        raise SheetsGatewayError("TAB_NOT_FOUND", "exact tab title was not found")

    def read_values(self, spreadsheet_id: str, sheet_title: str, cell_range: str) -> list[list[Any]]:
        self.get_sheet_metadata(spreadsheet_id, sheet_title)
        remote_range = quote("'" + sheet_title + "'!" + cell_range, safe="!'")
        response = self._request("GET", "/v4/spreadsheets/" + quote(spreadsheet_id, safe="") + "/values/" + remote_range)
        values = response.get("values", [])
        if not isinstance(values, list) or any(not isinstance(row, list) for row in values):
            raise SheetsGatewayError("MALFORMED_REMOTE_ROW", "values response must be a list of rows")
        return values

    def batch_update(self, spreadsheet_id: str, requests: list[dict[str, Any]]) -> None:
        if not isinstance(requests, list) or not requests:
            raise SheetsGatewayError("REMOTE_WRITE_FAILED", "batch update requires at least one request")
        if any(not isinstance(request, dict) or set(request) != {"appendCells"} for request in requests):
            raise SheetsGatewayError("REMOTE_WRITE_FAILED", "gateway permits appendCells requests only")
        self._request(
            "POST",
            "/v4/spreadsheets/" + quote(spreadsheet_id, safe="") + ":batchUpdate",
            payload={"requests": requests},
            write=True,
        )
