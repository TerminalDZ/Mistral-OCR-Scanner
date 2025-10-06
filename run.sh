#!/usr/bin/env bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export MISTRAL_API_KEY=your_key_here
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
