.venv\Scripts\python.exe -m compileall -q src tests

.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format --check .

.venv\Scripts\python.exe -m mypy src

.venv\Scripts\python.exe -m pytest
