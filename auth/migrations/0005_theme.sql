-- Tema de interfaz por cuenta (pedido explícito del usuario: cada cuenta
-- elige el suyo -- por ejemplo admin puede tener un tema distinto al de
-- un "user" cualquiera). Validado contra domain.users.THEMES, no aquí.
ALTER TABLE users ADD COLUMN theme text NOT NULL DEFAULT 'freya';
