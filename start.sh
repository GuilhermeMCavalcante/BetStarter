#!/bin/bash
exec streamlit run dashboard/dashboard.py \
  --server.port "${PORT:-8501}" \
  --server.address 0.0.0.0 \
  --server.headless true
