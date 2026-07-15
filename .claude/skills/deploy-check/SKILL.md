---
name: deploy-check
description: Пред-деплойная проверка Yummy перед пушем в main / Manual Deploy на Render.
allowed-tools: Bash, Read, Grep
---

# Pre-Deploy Checklist — Yummy

Выполнять последовательно. Остановиться на первом FAIL и показать, как чинить.

- [ ] `git status` — понять, что коммитится; секретов в staged нет
      (`git diff --cached | grep -iE "token|secret|sk-ant"` → пусто).
- [ ] `rm -f spasibox.db* && .venv/bin/python -m pytest -q` — все тесты зелёные.
- [ ] `.venv/bin/python -m py_compile app/*.py tools/*.py` — синтаксис ок.
- [ ] Если менялся фронт: `YUMMY_PAGES_API_BASE=https://yummy-astana.onrender.com make docs`
      и `grep -c "yummy-astana.onrender.com" docs/index.html` == нужное (витрина
      не сброшена в демо).
- [ ] Нет `print()` в проде (`grep -rn "print(" app | grep -v "#"`).
- [ ] Новые env задокументированы в `.env.example` и (если обязательны) в `render.yaml`.
- [ ] `.env` НЕ в staged.

Если всё ок — вывести:
```
✅ READY TO DEPLOY
Пуш: git push origin main
Затем: Render dashboard → yummy-astana → Manual Deploy → Deploy latest commit
(автодеплоя нет — репо подключён по public URL).
```
Если есть проблемы — полный список с командами-фиксами.
