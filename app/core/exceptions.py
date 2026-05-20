from fastapi import HTTPException, status


class AppError(HTTPException):
    def __init__(self, status_code: int, detail: str, code: str):
        super().__init__(status_code=status_code, detail={"detail": detail, "code": code})


def not_found(message: str = "Resource not found", code: str = "NOT_FOUND") -> AppError:
    return AppError(status.HTTP_404_NOT_FOUND, message, code)


def bad_request(message: str, code: str = "BAD_REQUEST") -> AppError:
    return AppError(status.HTTP_400_BAD_REQUEST, message, code)


def unauthorized(message: str = "Unauthorized", code: str = "UNAUTHORIZED") -> AppError:
    return AppError(status.HTTP_401_UNAUTHORIZED, message, code)


def forbidden(message: str = "Forbidden", code: str = "FORBIDDEN") -> AppError:
    return AppError(status.HTTP_403_FORBIDDEN, message, code)


def conflict(message: str, code: str = "CONFLICT") -> AppError:
    return AppError(status.HTTP_409_CONFLICT, message, code)


def too_many_requests(message: str, code: str = "RATE_LIMITED") -> AppError:
    return AppError(status.HTTP_429_TOO_MANY_REQUESTS, message, code)
