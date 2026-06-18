from __future__ import annotations

import re
from datetime import datetime, timedelta

import bcrypt
from sqlalchemy.orm import Session

from app.models.entities import User

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15
MIN_PASSWORD_LEN = 8
MIN_USERNAME_LEN = 3

VALID_ROLES = {"viewer", "analyst", "admin"}

ROLE_LABEL = {
    "viewer": "Básico",
    "analyst": "Analista",
    "admin": "Administrador",
}


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def _verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


def _validate_password(password: str) -> str | None:
    """Return error message or None if valid."""
    if len(password) < MIN_PASSWORD_LEN:
        return f"Senha deve ter pelo menos {MIN_PASSWORD_LEN} caracteres."
    if not re.search(r"[A-Z]", password):
        return "Senha deve conter pelo menos uma letra maiúscula."
    if not re.search(r"\d", password):
        return "Senha deve conter pelo menos um número."
    return None


def get_user(db: Session, username: str) -> User | None:
    return db.query(User).filter(User.username == username.strip().lower()).first()


def get_user_by_id(db: Session, user_id: int) -> User | None:
    return db.query(User).filter(User.id == user_id).first()


def list_users(db: Session) -> list[User]:
    return db.query(User).order_by(User.created_at.asc()).all()


def is_locked(user: User) -> bool:
    return bool(user.locked_until and user.locked_until > datetime.utcnow())


def authenticate(db: Session, username: str, password: str) -> tuple[User | None, str]:
    user = get_user(db, username)
    if not user:
        return None, "Usuário ou senha inválidos."
    if not user.is_active:
        return None, "Conta desativada. Entre em contato com o administrador."
    if is_locked(user):
        remaining = max(1, int((user.locked_until - datetime.utcnow()).total_seconds() / 60))
        return None, f"Conta bloqueada por tentativas excessivas. Tente novamente em {remaining} minuto(s)."

    if not _verify_password(password, user.password_hash):
        user.failed_attempts = (user.failed_attempts or 0) + 1
        if user.failed_attempts >= MAX_FAILED_ATTEMPTS:
            user.locked_until = datetime.utcnow() + timedelta(minutes=LOCKOUT_MINUTES)
            db.commit()
            return None, f"Muitas tentativas. Conta bloqueada por {LOCKOUT_MINUTES} minutos."
        db.commit()
        left = MAX_FAILED_ATTEMPTS - user.failed_attempts
        return None, f"Usuário ou senha inválidos. {left} tentativa(s) restante(s)."

    # Success — reset counters
    user.failed_attempts = 0
    user.locked_until = None
    user.last_login = datetime.utcnow()
    db.commit()
    return user, ""


def create_user(
    db: Session,
    username: str,
    password: str,
    role: str = "viewer",
    email: str | None = None,
) -> User:
    username = username.strip().lower()

    if len(username) < MIN_USERNAME_LEN:
        raise ValueError(f"Usuário deve ter pelo menos {MIN_USERNAME_LEN} caracteres.")
    if not re.match(r"^[a-z0-9_]+$", username):
        raise ValueError("Usuário pode conter apenas letras minúsculas, números e _.")
    if role not in VALID_ROLES:
        raise ValueError(f"Perfil inválido: {role}.")

    err = _validate_password(password)
    if err:
        raise ValueError(err)

    if get_user(db, username):
        raise ValueError(f"Usuário '{username}' já existe.")

    user = User(
        username=username,
        email=email.strip().lower() if email else None,
        password_hash=_hash_password(password),
        role=role,
        is_active=True,
        failed_attempts=0,
        created_at=datetime.utcnow(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_role(db: Session, user_id: int, new_role: str) -> User:
    if new_role not in VALID_ROLES:
        raise ValueError(f"Perfil inválido: {new_role}.")
    user = get_user_by_id(db, user_id)
    if not user:
        raise ValueError("Usuário não encontrado.")
    user.role = new_role
    db.commit()
    return user


def set_active(db: Session, user_id: int, active: bool) -> User:
    user = get_user_by_id(db, user_id)
    if not user:
        raise ValueError("Usuário não encontrado.")
    user.is_active = active
    db.commit()
    return user


def unlock_user(db: Session, user_id: int) -> User:
    user = get_user_by_id(db, user_id)
    if not user:
        raise ValueError("Usuário não encontrado.")
    user.failed_attempts = 0
    user.locked_until = None
    db.commit()
    return user


def change_password(db: Session, user_id: int, new_password: str) -> None:
    err = _validate_password(new_password)
    if err:
        raise ValueError(err)
    user = get_user_by_id(db, user_id)
    if not user:
        raise ValueError("Usuário não encontrado.")
    user.password_hash = _hash_password(new_password)
    user.failed_attempts = 0
    user.locked_until = None
    db.commit()
