import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

import streamlit as st
from app.config import settings, validate_world_cup_scope
from dotenv import load_dotenv

load_dotenv()
st.set_page_config(page_title="World Cup Bet Recommender", layout="wide")
st.title("World Cup Bet Recommender MVP")
st.caption("Modelo v1: ratings das seleções + Poisson + filtro de EV. Ferramenta analítica; não garante lucro.")
league, season = validate_world_cup_scope()
st.sidebar.info(f"Competicao: FIFA World Cup\n\nLeague ID: {league}\n\nSeason: {season}")
limit = st.sidebar.slider("Quantidade", 10, 200, 50)
bankroll = st.sidebar.number_input("Banca", min_value=1.0, value=settings.default_bankroll, step=50.0)
days = st.sidebar.slider("Buscar próximos dias", 1, 30, 7)