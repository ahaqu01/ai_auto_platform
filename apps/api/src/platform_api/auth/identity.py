from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IdentityClaims:
    issuer: str
    subject: str
    email: str
    display_name: str
