import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv
load_dotenv(ROOT_DIR / ".env")

from datetime import datetime, timezone

import streamlit as st

from app.db.session import SessionLocal
from app.services.auth import (
    ROLE_LABEL,
    VALID_ROLES,
    change_password,
    create_user,
    is_locked,
    list_users,
    set_active,
    unlock_user,
    update_role,
)

# ── Guard ── só admin chega aqui via st.navigation, mas validamos por segurança
if not st.session_state.get("user") or st.session_state.user["role"] != "admin":
    st.error("Acesso negado.")
    st.stop()

st.title("👥 Gerenciamento de Usuários")

current_user_id = st.session_state.user["id"]

# ── Lista de usuários ──────────────────────────────────────────────────────────
with SessionLocal() as db:
    users = list_users(db)

st.subheader("Usuários cadastrados")

for u in users:
    is_me = u.id == current_user_id
    locked = is_locked(u)

    status_badge = "🔴 Bloqueado" if locked else ("🟢 Ativo" if u.is_active else "⚫ Inativo")
    me_badge = " · **Você**" if is_me else ""

    with st.expander(f"**{u.username}** — {ROLE_LABEL.get(u.role, u.role)} · {status_badge}{me_badge}"):
        col_info, col_actions = st.columns([2, 1])

        with col_info:
            st.markdown(f"- **E-mail:** {u.email or '—'}")
            st.markdown(f"- **Criado em:** {u.created_at.strftime('%d/%m/%Y %H:%M') if u.created_at else '—'}")
            last = u.last_login
            st.markdown(f"- **Último login:** {last.strftime('%d/%m/%Y %H:%M') if last else 'Nunca'}")
            if locked:
                st.warning(f"Bloqueado até {u.locked_until.strftime('%d/%m/%Y %H:%M')}")

        with col_actions:
            # Alterar perfil
            current_role_idx = list(VALID_ROLES).index(u.role) if u.role in VALID_ROLES else 0
            role_options = list(VALID_ROLES)
            new_role = st.selectbox(
                "Perfil",
                options=role_options,
                index=role_options.index(u.role) if u.role in role_options else 0,
                format_func=lambda r: ROLE_LABEL.get(r, r),
                key=f"role_{u.id}",
                disabled=is_me,
            )
            if not is_me and st.button("Salvar perfil", key=f"save_role_{u.id}", use_container_width=True):
                try:
                    with SessionLocal() as db:
                        update_role(db, u.id, new_role)
                    st.success("Perfil atualizado.")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))

            st.divider()

            # Ativar/Desativar
            if not is_me:
                label = "Desativar conta" if u.is_active else "Ativar conta"
                if st.button(label, key=f"toggle_{u.id}", use_container_width=True,
                             type="secondary"):
                    with SessionLocal() as db:
                        set_active(db, u.id, not u.is_active)
                    st.rerun()

            # Desbloquear
            if locked:
                if st.button("Desbloquear", key=f"unlock_{u.id}", use_container_width=True):
                    with SessionLocal() as db:
                        unlock_user(db, u.id)
                    st.success("Conta desbloqueada.")
                    st.rerun()

st.divider()

# ── Criar novo usuário ─────────────────────────────────────────────────────────
st.subheader("Criar novo usuário")
with st.form("new_user_form"):
    nc1, nc2 = st.columns(2)
    with nc1:
        new_username = st.text_input("Usuário")
        new_password = st.text_input("Senha", type="password",
                                     help="Mín. 8 caracteres, 1 maiúscula e 1 número.")
    with nc2:
        new_email = st.text_input("E-mail (opcional)")
        new_role = st.selectbox(
            "Perfil",
            options=list(VALID_ROLES),
            format_func=lambda r: ROLE_LABEL.get(r, r),
        )
    submitted = st.form_submit_button("Criar usuário", type="primary", use_container_width=True)

if submitted:
    try:
        with SessionLocal() as db:
            user = create_user(db, new_username, new_password, role=new_role,
                               email=new_email or None)
        st.success(f"Usuário '{user.username}' criado com perfil {ROLE_LABEL.get(user.role)}.")
        st.rerun()
    except ValueError as e:
        st.error(str(e))

st.divider()

# ── Alterar minha senha ────────────────────────────────────────────────────────
st.subheader("Alterar minha senha")
with st.form("change_pw_form"):
    new_pw = st.text_input("Nova senha", type="password",
                           help="Mín. 8 caracteres, 1 maiúscula e 1 número.")
    new_pw2 = st.text_input("Confirmar nova senha", type="password")
    pw_submitted = st.form_submit_button("Alterar senha", use_container_width=True)

if pw_submitted:
    if new_pw != new_pw2:
        st.error("As senhas não coincidem.")
    else:
        try:
            with SessionLocal() as db:
                change_password(db, current_user_id, new_pw)
            st.success("Senha alterada com sucesso.")
        except ValueError as e:
            st.error(str(e))
