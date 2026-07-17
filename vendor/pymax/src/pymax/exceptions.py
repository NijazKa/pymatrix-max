from typing import Any


class PyMaxError(Exception):
    pass


class UploadError(PyMaxError):
    pass


class ApiError(PyMaxError):
    def __init__(
        self,
        *,
        opcode: int,
        error: str | None = None,
        message: str | None = None,
        localized_message: str | None = None,
        title: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.opcode = opcode
        self.error = error
        self.message = message
        self.localized_message = localized_message
        self.title = title
        self.payload = payload or {}

        parts = []
        for part in (localized_message, message):
            if part and part not in parts:
                parts.append(part)
        if title:
            parts.append(f"({title})")
        if error:
            parts.append(f"[{error}]")

        text = " ".join(parts) or "API request failed"

        super().__init__(text)
