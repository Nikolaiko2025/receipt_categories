-- Уникальность логина пользователя (лабораторная 4).
-- Проверка в приложении остаётся, но БД тоже должна гарантировать
-- отсутствие двух пользователей с одинаковым username.
--
-- Выполнить один раз:
--   psql -U Nikolai -d receipt_categories -f db/migrations/001_users_username_unique.sql

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'users_username_key'
    ) THEN
        ALTER TABLE users
            ADD CONSTRAINT users_username_key UNIQUE (username);
    END IF;
END $$;
