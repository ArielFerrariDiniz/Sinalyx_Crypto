import secrets
from dataclasses import dataclass, field

from ..models import Credentials


class SessionNotFound(Exception):
    pass


class SessionLimitReached(Exception):
    pass


@dataclass(repr=False)
class Session:
    credentials: Credentials | None
    warnings: list[str] = field(default_factory=list)


class SessionStore:
    def __init__(self):
        self._sessions: dict[str, Session] = {}

    def create(self, credentials: Credentials | None, warnings: list[str]) -> str:
        # Limite defensivo para o processo local; não há usuários persistidos.
        if len(self._sessions) >= 16:
            raise SessionLimitReached()
        token = secrets.token_urlsafe(32)
        self._sessions[token] = Session(credentials, warnings)
        return token

    def require(self, token: str | None) -> Session:
        session = self._sessions.get(token or "")
        if session is None:
            raise SessionNotFound()
        return session

    def delete(self, token: str | None):
        session = self._sessions.pop(token or "", None)
        if session is not None:
            session.credentials = None
            session.warnings.clear()

    def update_credentials(self, credentials: Credentials, warnings: list[str]):
        for session in self._sessions.values():
            session.credentials = credentials
            session.warnings = warnings.copy()

    def clear(self):
        for token in list(self._sessions):
            self.delete(token)
