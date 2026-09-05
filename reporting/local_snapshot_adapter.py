"""In-memory Sheets-shaped adapter for deterministic Snapshot MVP dry runs.

This module has no Google credentials or network calls. It deliberately accepts only
the append-only request shape emitted by snapshot_mvp so a test can exercise
read -> append -> readback without touching an actual spreadsheet.
"""

import copy

from reporting.snapshot_mvp import COLUMNS, digest


class LocalSheetAdapter:
    """Ephemeral storage adapter; discard the instance to remove all test rows."""

    def __init__(self, sheet_id, values=None):
        if type(sheet_id) is not int or sheet_id < 0:
            raise ValueError("Require a metadata-grounded sheetId")
        self.sheet_id = sheet_id
        self._values = copy.deepcopy(values if values is not None else [COLUMNS])

    def read_values(self):
        return copy.deepcopy(self._values)

    def apply(self, plan):
        if plan["precondition_hash"] != digest(self._values):
            raise ValueError("Storage changed after planning; re-read before append")
        for request in plan["requests"]:
            append = request.get("appendCells")
            if not append or set(request) != {"appendCells"}:
                raise ValueError("Only appendCells requests are allowed")
            if append.get("sheetId") != self.sheet_id:
                raise ValueError("Request targets a different sheet")
            if append.get("fields") != "userEnteredValue,userEnteredFormat":
                raise ValueError("Unexpected write fields")
            for row in append.get("rows", []):
                cells = row.get("values", [])
                if len(cells) != len(COLUMNS):
                    raise ValueError("Row width does not match the snapshot schema")
                values = []
                for cell in cells:
                    entered = cell.get("userEnteredValue")
                    if entered is None:
                        values.append("")
                    elif set(entered) == {"stringValue"}:
                        values.append(entered["stringValue"])
                    elif set(entered) == {"numberValue"}:
                        values.append(entered["numberValue"])
                    else:
                        raise ValueError("Unexpected cell value type")
                self._values.append(values)
