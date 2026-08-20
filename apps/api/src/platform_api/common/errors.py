from dataclasses import dataclass


@dataclass(slots=True)
class DomainError(Exception):
    code: str
    safe_detail: str
    http_status: int = 400

    def __str__(self) -> str:
        return self.safe_detail
