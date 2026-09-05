"""Append-only Google Sheets persistence for validated snapshot candidates.

The gateway is injected so credentials and transport stay outside the repository.
This adapter assumes exactly one writer performs read -> append -> readback.
"""

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from reporting.snapshot_mvp import (
    COLUMNS,
    KEY_FIELDS,
    digest,
    plan_sheet_append,
    parse_sheet_values,
    validate_history,
    validate_payload,
    verify_readback,
)


class SheetSchemaError(ValueError):
    """The live sheet cannot safely represent the snapshot contract."""

    def __init__(self, code: str, detail: str):
        super().__init__(code + ": " + detail)
        self.code = code


class SheetsGateway(Protocol):
    """Small transport boundary for an authenticated Google Sheets client."""

    def read_values(self, spreadsheet_id: str, sheet_title: str, cell_range: str) -> list[list[Any]]:
        ...

    def batch_update(self, spreadsheet_id: str, requests: list[dict[str, Any]]) -> None:
        ...


@dataclass(frozen=True)
class StorageResult:
    storage_status: str
    data_status: str
    appended_count: int | None
    detail: str
    failure_code: str | None = None


def _column_label(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


class GoogleSheetsSnapshotAdapter:
    """Schema-checked, append-only adapter; it does not claim multi-writer safety."""

    def __init__(
        self,
        gateway: SheetsGateway,
        spreadsheet_id: str,
        sheet_title: str,
        sheet_id: int,
        *,
        header_row: int = 1,
        max_rows: int = 1000,
        header_mapping: Mapping[str, str] | None = None,
    ):
        if not spreadsheet_id or not sheet_title or type(sheet_id) is not int or sheet_id < 0:
            raise ValueError("Require metadata-grounded spreadsheet and sheet identifiers")
        if type(header_row) is not int or header_row < 1 or type(max_rows) is not int or max_rows < header_row:
            raise ValueError("Invalid metadata-grounded sheet bounds")
        mapping = dict(header_mapping or {})
        if set(mapping) - set(COLUMNS):
            raise SheetSchemaError("SCHEMA_MISMATCH", "Header mapping contains unknown contract fields")
        self.remote_headers = tuple(mapping.get(column, column) for column in COLUMNS)
        if len(set(self.remote_headers)) != len(self.remote_headers) or any(not header for header in self.remote_headers):
            raise SheetSchemaError("SCHEMA_MISMATCH", "Header mapping must be one-to-one and nonempty")
        self.gateway = gateway
        self.spreadsheet_id = spreadsheet_id
        self.sheet_title = sheet_title
        self.sheet_id = sheet_id
        self.header_row = header_row
        self.max_rows = max_rows
        self.read_range = "A1:" + _column_label(len(COLUMNS)) + str(max_rows)

    def _canonical_values_with_headers(self) -> tuple[list[list[Any]], list[str]]:
        metadata_reader = getattr(self.gateway, "get_sheet_metadata", None)
        if callable(metadata_reader):
            properties = metadata_reader(self.spreadsheet_id, self.sheet_title)
            if not isinstance(properties, dict) or properties.get("sheetId") != self.sheet_id:
                raise SheetSchemaError("TAB_NOT_FOUND", "Configured sheetId does not match the exact tab title")
        values = self.gateway.read_values(self.spreadsheet_id, self.sheet_title, self.read_range)
        if not isinstance(values, list) or len(values) < self.header_row:
            raise SheetSchemaError("SCHEMA_MISMATCH", "Sheet is unavailable or missing the configured header row")
        if any(not isinstance(row, list) for row in values):
            raise SheetSchemaError("MALFORMED_REMOTE_ROW", "Sheet values must be rows")
        headers = list(values[self.header_row - 1])
        if any(not isinstance(header, str) or not header for header in headers):
            raise SheetSchemaError("SCHEMA_MISMATCH", "Snapshot headers must be nonempty text")
        if len(headers) != len(set(headers)):
            raise SheetSchemaError("DUPLICATE_HEADER", "Duplicate snapshot header")
        if set(headers) != set(self.remote_headers) or len(headers) != len(self.remote_headers):
            missing = sorted(set(self.remote_headers) - set(headers))
            unexpected = sorted(set(headers) - set(self.remote_headers))
            raise SheetSchemaError("SCHEMA_MISMATCH", "Header mismatch; missing=" + repr(missing) + "; unexpected=" + repr(unexpected))
        positions = {header: index for index, header in enumerate(headers)}
        canonical = [list(COLUMNS)]
        for cells in values[self.header_row:]:
            if len(cells) > len(headers):
                raise SheetSchemaError("MALFORMED_REMOTE_ROW", "Remote row exceeds the contract width")
            padded = list(cells) + [""] * (len(headers) - len(cells))
            canonical.append([padded[positions[header]] for header in self.remote_headers])
        return canonical, headers

    def _canonical_values(self) -> list[list[Any]]:
        return self._canonical_values_with_headers()[0]

    def read_snapshots(self) -> list[dict[str, Any]]:
        return parse_sheet_values(self._canonical_values())

    def find_existing_business_key(self, candidate: Mapping[str, Any]) -> dict[str, Any] | None:
        validate_payload(dict(candidate))
        logical_key = digest([candidate[field] for field in KEY_FIELDS])
        return validate_history(self.read_snapshots()).get(logical_key)

    def resolve_latest_revision(self, candidate: Mapping[str, Any]) -> dict[str, Any] | None:
        return self.find_existing_business_key(candidate)

    def _append_request(self, appended: list[dict[str, Any]], headers: list[str]) -> list[dict[str, Any]]:
        if not appended:
            return []
        remote_to_contract = {remote: contract for contract, remote in zip(COLUMNS, self.remote_headers)}
        rows = []
        for snapshot in appended:
            cells = []
            for header in headers:
                field = remote_to_contract[header]
                value = snapshot[field]
                cell = {"userEnteredFormat": {"verticalAlignment": "TOP", "wrapStrategy": "CLIP"}}
                if value is not None:
                    cell["userEnteredValue"] = {"numberValue" if type(value) in (int, float) else "stringValue": value}
                cells.append(cell)
            rows.append({"values": cells})
        return [{"appendCells": {"sheetId": self.sheet_id, "rows": rows,
                                 "fields": "userEnteredValue,userEnteredFormat"}}]

    def append_if_new(self, candidates: list[dict[str, Any]]) -> StorageResult:
        """Read -> plan -> append -> readback. Never replay an uncertain write."""
        try:
            existing, headers = self._canonical_values_with_headers()
            parse_sheet_values(existing)
        except SheetSchemaError as error:
            return StorageResult("Failed", "Failed", 0, "Storage schema rejected write: " + str(error), error.code)
        except ValueError as error:
            return StorageResult("Failed", "Failed", 0, "Malformed remote history: " + str(error), "MALFORMED_REMOTE_ROW")
        except Exception as error:
            return StorageResult("Failed", "Failed", 0, "Remote read rejected write: " + str(error), getattr(error, "code", "REMOTE_READ_FAILED"))
        try:
            plan = plan_sheet_append(self.sheet_id, existing, candidates)
        except (ValueError, TypeError) as error:
            return StorageResult("Failed", "Failed", 0, "Snapshot validation rejected write: " + str(error), "INVALID_SNAPSHOT")
        if not plan["append"]:
            return StorageResult("Ready", "Ready", 0, "Idempotent no-op")
        try:
            self.gateway.batch_update(self.spreadsheet_id, self._append_request(plan["append"], headers))
        except Exception as error:
            if getattr(error, "code", None) != "WRITE_RESULT_UNCERTAIN":
                return StorageResult("Failed", "Failed", None, "Remote write failed; do not replay: " + str(error), getattr(error, "code", "REMOTE_WRITE_FAILED"))
            try:
                verify_readback(plan, self._canonical_values())
            except Exception as reconciliation_error:
                return StorageResult("Failed", "Failed", None, "Uncertain write could not be reconciled; do not replay: " + str(reconciliation_error), "WRITE_RESULT_UNCERTAIN")
            return StorageResult("Ready", "Ready", len(plan["append"]), "Uncertain write reconciled by readback")
        try:
            verify_readback(plan, self._canonical_values())
        except Exception as error:
            return StorageResult("Failed", "Failed", None, "Post-write readback failed; do not replay: " + str(error), getattr(error, "code", "READBACK_MISMATCH"))
        return StorageResult("Ready", "Ready", len(plan["append"]), "Append and readback passed")

    def append_snapshots(self, candidates: list[dict[str, Any]]) -> StorageResult:
        return self.append_if_new(candidates)
