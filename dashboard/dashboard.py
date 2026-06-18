import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv
load_dotenv(ROOT_DIR / ".env")

import streamlit as st

from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.services.auth import (
    ROLE_LABEL,
    authenticate,
    create_user,
    list_users,
)

init_db()

st.set_page_config(page_title="BetStarter", layout="wide", page_icon="⚽")

# ── Session bootstrap ──────────────────────────────────────────────────────────
if "user" not in st.session_state:
    st.session_state.user = None

PAGES = Path(__file__).resolve().parent / "pages"


# ── First-run setup (no users in DB yet) ──────────────────────────────────────
def _first_run_setup():
    st.markdown(
        "<h2 style='text-align:center'>⚽ BetStarter — Configuração Inicial</h2>",
        unsafe_allow_html=True,
    )
    st.info("Nenhum usuário cadastrado. Crie o primeiro administrador para começar.")
    with st.form("setup_form"):
        username = st.text_input("Usuário administrador")
        email = st.text_input("E-mail (opcional)")
        password = st.text_input("Senha", type="password",
                                 help="Mín. 8 caracteres, 1 maiúscula e 1 número.")
        password2 = st.text_input("Confirmar senha", type="password")
        submitted = st.form_submit_button("Criar administrador", type="primary",
                                          use_container_width=True)
    if submitted:
        if password != password2:
            st.error("As senhas não coincidem.")
            return
        try:
            with SessionLocal() as db:
                user = create_user(db, username, password, role="admin",
                                   email=email or None)
            st.success(f"Administrador '{user.username}' criado com sucesso! Faça login.")
            st.rerun()
        except ValueError as e:
            st.error(str(e))


# ── Login / register form ──────────────────────────────────────────────────────
def _show_auth():
    _, col, _ = st.columns([1, 1.6, 1])
    with col:
        st.markdown(
            "<h2 style='text-align:center'>⚽ BetStarter</h2>"
            "<p style='text-align:center; color:#888'>FIFA World Cup 2026 · Análise estatística</p>",
            unsafe_allow_html=True,
        )
        st.divider()
        tab_login, tab_register = st.tabs(["🔑 Entrar", "📝 Criar conta"])

        with tab_login:
            with st.form("login_form"):
                username = st.text_input("Usuário")
                password = st.text_input("Senha", type="password")
                submitted = st.form_submit_button("Entrar", type="primary",
                                                  use_container_width=True)
            if submitted:
                if not username or not password:
                    st.error("Preencha usuário e senha.")
                else:
                    with SessionLocal() as db:
                        user, msg = authenticate(db, username, password)
                    if user:
                        st.session_state.user = {
                            "id": user.id,
                            "username": user.username,
                            "role": user.role,
                        }
                        st.rerun()
                    else:
                        st.error(msg)

        with tab_register:
            st.caption("Novas contas começam com perfil **Básico**. "
                       "Um administrador pode alterar o perfil depois.")
            with st.form("register_form"):
                new_user = st.text_input("Usuário", help="Letras minúsculas, números e _ apenas.")
                new_email = st.text_input("E-mail (opcional)")
                new_pass = st.text_input("Senha", type="password",
                                         help="Mín. 8 caracteres, 1 maiúscula e 1 número.")
                new_pass2 = st.text_input("Confirmar senha", type="password")
                submitted_reg = st.form_submit_button("Criar conta", use_container_width=True)
            if submitted_reg:
                if new_pass != new_pass2:
                    st.error("As senhas não coincidem.")
                else:
                    try:
                        with SessionLocal() as db:
                            create_user(db, new_user, new_pass, role="viewer",
                                        email=new_email or None)
                        st.success("Conta criada! Faça login na aba **Entrar**.")
                    except ValueError as e:
                        st.error(str(e))


# ── Check first run ────────────────────────────────────────────────────────────
with SessionLocal() as db:
    no_users = len(list_users(db)) == 0

if no_users:
    _first_run_setup()
    st.stop()

if not st.session_state.user:
    _show_auth()
    st.stop()

# ── Authenticated — build navigation ──────────────────────────────────────────
user = st.session_state.user
role = user["role"]

# Sidebar: identity + logout
with st.sidebar:
    st.markdown(
        f"👤 **{user['username']}**  \n"
        f"`{ROLE_LABEL.get(role, role)}`"
    )
    if st.button("Sair", use_container_width=True):
        st.session_state.user = None
        st.rerun()
    st.divider()

# ── Page registry ──────────────────────────────────────────────────────────────
home_pg        = st.Page(str(PAGES / "home.py"),            title="Home",        icon="⚽", default=True)
palpites_pg    = st.Page(str(PAGES / "palpites.py"),        title="Palpites",    icon="🎯")
performance_pg = st.Page(str(PAGES / "recommendations.py"), title="Performance", icon="📈")
model_pg       = st.Page(str(PAGES / "modelo.py"),          title="Modelo",      icon="🧠")
analise_pg     = st.Page(str(PAGES / "analise.py"),         title="Análise",     icon="🔬")
telegram_pg    = st.Page(str(PAGES / "telegram.py"),        title="Telegram",    icon="📨")
admin_pg       = st.Page(str(PAGES / "admin.py"),           title="Usuários",    icon="👥")

# ── Access matrix ──────────────────────────────────────────────────────────────
#  viewer   → Home, Palpites
#  analyst  → Home, Palpites, Performance, Modelo, Análise
#  admin    → tudo + Telegram + Usuários
if role == "viewer":
    pages = [home_pg, palpites_pg]
elif role == "analyst":
    pages = [home_pg, palpites_pg, performance_pg, model_pg, analise_pg]
else:  # admin
    pages = [home_pg, palpites_pg, performance_pg, model_pg, analise_pg,
             telegram_pg, admin_pg]

pg = st.navigation(pages)
pg.run()
