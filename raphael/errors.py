"""Only these deliberately written messages may cross the API boundary."""

class AppError(Exception):
    def __init__(self, message: str, status: int = 400, code: str = "invalid_request"):
        super().__init__(message)
        self.status = status
        self.code = code


class Cancelled(Exception):
    """Internal control flow; cancellation is not an application error."""
