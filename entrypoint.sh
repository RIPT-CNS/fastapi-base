#!/bin/sh

if [ "$DEBUG" = "true" ]; then
    pip install -r requirements-local.txt
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
else
    pip install -r requirements-local.txt
    exec gunicorn app.main:app --workers 17 --worker-class uvicorn.workers.UvicornWorker --threads 8 --timeout 120 --keep-alive 5 --bind 0.0.0.0:8000
fi
