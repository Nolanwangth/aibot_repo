#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
export $(cat .env | xargs)
python -m src.main
