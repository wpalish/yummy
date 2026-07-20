# Восстановление БД (runbook)

> Репетиция проведена 2026-07-20 на проекте `yummy-test` (cmgjwncezxqgqdqconoh):
> схема восстановлена из прод-каталога, сигнатуры схем прод↔тест совпали
> (md5 `74d058c94d831534361eef4c2f21ddab`, 18 таблиц), вставка/чтение данных
> всех типов проверены. Реальные пользовательские данные (хеши паролей,
> refresh-токены) между базами НЕ копировались — намеренно.

## Сценарий А: откат прод-базы (Supabase backups)

1. Supabase Dashboard → проект `yummy-production` → Database → Backups.
   На free-плане — daily backups; выбрать точку и **Restore**.
2. После восстановления Render НЕ трогать: приложение схемо-миграции делает
   само на старте (`CREATE TABLE IF NOT EXISTS` + `ADD COLUMN IF NOT EXISTS`),
   недостающие новые колонки дольются автоматически.
3. Smoke: `curl https://yummy-astana.onrender.com/health` → `"status":"ok"`,
   вход админа (2FA), список пользователей в админке.
4. Побочный эффект отката: refresh-токены откатились → у части пользователей
   сессии умрут (войдут заново) — это нормально.

## Сценарий Б: миграция на новую базу (Supabase умер целиком)

1. Создать новый проект → взять Session pooler URL (:5432).
2. На Render: Environment → `DATABASE_URL` = новый URL → Save, rebuild, deploy.
   Приложение создаст пустую схему само.
3. Данные из последнего дампа: `psql "$NEW_URL" < dump.sql`
   (дамп: `pg_dump --data-only --schema=public "$OLD_URL" > dump.sql` — делать
   регулярно, см. ниже).
4. Проверить сигнатуру схемы (обе базы):
   ```sql
   SELECT md5(string_agg(table_name||':'||column_name||':'||data_type,
          ',' ORDER BY table_name, ordinal_position))
   FROM information_schema.columns WHERE table_schema='public';
   ```
   Совпала → структура идентична.
5. `REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated;`
   (приложение ходит через pooler-роль, PostgREST-доступ не нужен).

## Регулярный дамп (пока нет платного PITR)

Раз в неделю локально:
```bash
pg_dump --schema=public "$DATABASE_URL" | gzip > backups/yummy-$(date +%F).sql.gz
```
Хранить вне ноутбука (облако). Проверять восстановление раз в квартал —
на `yummy-test`, схема там уже развёрнута и совпадает с продом.

## Чего НЕ делать

- Не восстанавливать дамп поверх живой базы без остановки записи
  (Render → Suspend service на время restore).
- Не копировать прод-данные (pw_hash, токены) в тестовые базы.
