-- Corrige el modelo de roles: "role" vuelve a ser sólo user|admin (un tipo
-- de cuenta), no un role por servicio (git_user, storage_user, ...) --
-- eso impedía combinar accesos (alguien con git Y cicd no tenía ningún
-- role válido). Los permisos de servicio de una cuenta "user" ahora se
-- guardan aparte, en una lista libre -- mismo patrón que ya usa
-- service_accounts.permissions.
ALTER TABLE users ADD COLUMN extra_permissions text[] NOT NULL DEFAULT '{}';
