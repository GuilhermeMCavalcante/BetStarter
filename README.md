# World Cup Bet Recommender MVP

MVP travado para Copa do Mundo usando API-Football v3.

Esta versao inclui:

- Dashboard Streamlit com botao de atualizacao
- Coleta de jogos e odds
- Ratings iniciais das selecoes
- Modelo v1 com Poisson + ratings + stats quando existirem
- Filtro de EV e Edge
- Aba de debug mostrando odds rejeitadas e motivo
- Aba de jogos encontrados

> Aviso: ferramenta analitica. Nao existe garantia de lucro em apostas.

## Instalar no Windows

Dentro da pasta do projeto:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
```

Crie o arquivo `.env` a partir do exemplo:

```powershell
Copy-Item .env.example .env
```

Edite o `.env` e coloque sua chave:

```env
API_FOOTBALL_KEY=sua_chave_aqui
WORLD_CUP_ONLY=true
WORLD_CUP_LEAGUE_ID=1
WORLD_CUP_SEASON=2026
MIN_EV=0.05
DEFAULT_BANKROLL=1000
```

## Rodar

```powershell
$env:PYTHONPATH="."
py scripts\init_db.py
py -m streamlit run .\dashboard\dashboard.py
```

No dashboard, clique em **Atualizar recomendações da Copa**.

## Rodar pipeline manualmente

```powershell
$env:PYTHONPATH="."
py scripts\pipeline.py --days 7
```

Exemplo de saida esperada:

```text
{'competition': 'FIFA World Cup', 'league': 1, 'season': 2026, 'fixtures': 15, 'odds': 1357, 'ratings_seeded': 48, 'stats': 1, 'odds_analyzed': 300, 'recommendations': 8}
```

## O que o modelo faz

Para Over 1.5, Over 2.5 e Ambas Marcam:

1. Usa rating inicial das selecoes.
2. Estima gols esperados de cada lado.
3. Calcula probabilidade via Poisson.
4. Usa stats recentes da propria Copa quando existirem.
5. Compara com probabilidade implicita da odd.
6. Aprova somente se EV e Edge passarem no filtro.

## Onde ajustar ratings

Arquivo:

```text
app/services/worldcup_model.py
```

Procure por:

```python
DEFAULT_TEAM_RATINGS = {
    "Argentina": 92,
    "France": 91,
    ...
}
```

## Onde ajustar filtros

Arquivo `.env`:

```env
MIN_EV=0.05
```

Ou no arquivo:

```text
app/services/recommender.py
```

Filtros principais:

```python
if ev < min_ev:
if edge < 0.03:
if output.confidence_score < 55:
```

## Problemas comuns

### Dashboard sem entradas

Vá na aba **Rejeitadas / Debug**. Se houver odds rejeitadas, o sistema está funcionando e o filtro não encontrou EV suficiente.

### Jogos aparecem mas não há recomendações

Pode acontecer quando as odds estão eficientes ou quando o modelo está conservador. Diminua `MIN_EV` temporariamente para testar:

```env
MIN_EV=0.02
```

### Erro de pacote app

Rode sempre assim:

```powershell
$env:PYTHONPATH="."
py -m streamlit run .\dashboard\dashboard.py
```
