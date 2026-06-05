@echo off
set PYTHONUNBUFFERED=1
set PYTHONDONTWRITEBYTECODE=1
cd /d C:\Users\liangjunming\Desktop\AI_Project\backend_django
python -m daphne -b 0.0.0.0 -p 8767 config.asgi:application
