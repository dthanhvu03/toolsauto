#!/bin/bash
cd /home/vu/toolsauto
venv/bin/python -m py_compile $(find app -name '*.py')
venv/bin/python -c "from app.main import app; print('ROUTES: ', len(app.routes))"
venv/bin/python -c "from app.features.tiktok.adapter import TiktokAdapter; print('IMPORT OK')"
