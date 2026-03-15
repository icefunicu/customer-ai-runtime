from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class DiagnosticsJsonlExporter:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def export(self, event_payload: dict[str, Any]) -> None:
        # Best-effort, append-only. Failures should not break the request path.
        try:
            line = json.dumps(event_payload, ensure_ascii=False)
            self._path.open("a", encoding="utf-8").write(f"{line}\n")
        except Exception:
            return
