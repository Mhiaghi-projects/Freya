-- Fuerza un cambio de contraseña en el primer login: usado por el arranque
-- del primer admin (creado a mano en gestor-db, no por sign-up público),
-- pero disponible como campo general para cualquier cuenta sembrada así.

ALTER TABLE users ADD COLUMN must_change_password boolean NOT NULL DEFAULT false;
