# Yummy — весь проект одной командой (DX-паттерн из wasp)
PY := .venv/bin/python

.PHONY: dev test docs zip seed clean help

help:            ## список команд
	@grep -E '^[a-z]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-8s %s\n", $$1, $$2}'

dev:             ## запустить бэкенд на :8021
	$(PY) -m uvicorn app.main:app --reload --port 8021

test:            ## прогнать все тесты
	rm -f spasibox.db && $(PY) -m pytest -q

docs:            ## пересобрать статическую версию для GitHub Pages
	$(PY) tools/build_docs.py

seed:            ## пересоздать демо-данные
	rm -f spasibox.db && $(PY) -c "from app.db import Store; from app.seed import seed; seed(Store())"

backup:          ## консистентный бэкап БД в backups/ (безопасен при живом WAL)
	$(PY) tools/backup_db.py

zip:             ## собрать архив проекта в ~/Downloads/yummy.zip
	cd .. && rm -f ~/Downloads/yummy.zip && zip -r -q ~/Downloads/yummy.zip spasibox \
	  -x "spasibox/.venv/*" "spasibox/.git/*" "*/__pycache__/*" "*.pyc" "spasibox/*.db" "spasibox/.pytest_cache/*"

clean:           ## удалить локальную БД и кеши
	rm -f spasibox.db && rm -rf .pytest_cache app/__pycache__ tests/__pycache__
