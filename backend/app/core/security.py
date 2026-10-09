"""Hash de senha (Argon2id) e emissão/validação de JWT."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError

from app.core.config import settings
from app.core.errors import AuthenticationError

_hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)

TOKEN_TYPE = "access"


def hash_password(password: str) -> str:
    """Gera o hash Argon2id da senha."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Compara senha em texto com o hash armazenado, sem lançar exceção."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, ValueError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """Indica se o hash deve ser regerado com os parâmetros atuais."""
    try:
        return bool(_hasher.check_needs_rehash(password_hash))
    except Exception:  # pragma: no cover - hash corrompido
        return False


def create_access_token(
    *,
    user_id: uuid.UUID,
    organization_id: uuid.UUID,
    role: str,
    email: str,
    expires_minutes: int | None = None,
) -> str:
    """Emite um JWT HS256 com as claims mínimas necessárias."""
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=expires_minutes or settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "org": str(organization_id),
        "role": role,
        "email": email,
        "type": TOKEN_TYPE,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """Valida assinatura e expiração, devolvendo as claims."""
    try:
        claims: dict[str, Any] = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Sessão expirada. Faça login novamente.") from exc
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Token inválido.") from exc
    if claims.get("type") != TOKEN_TYPE:
        raise AuthenticationError("Token inválido.")
    return claims
