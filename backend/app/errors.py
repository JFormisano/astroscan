"""User-facing errors. Owner: Person A.

Every failure a user can hit carries a stable `code`, a plain `message` and a
`next_step`, so the frontend can show something useful without parsing strings.
Serialised by the handler in main.py as {"detail": {"code", "message", "next_step"}}.
"""


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, next_step: str = ""):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.next_step = next_step

    def to_detail(self) -> dict:
        return {"code": self.code, "message": self.message, "next_step": self.next_step}
