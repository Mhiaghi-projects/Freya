-- Papelera por usuario (pedido explícito del usuario). Antes, DELETE
-- borraba bytes y versiones al instante -- deleted_at sólo marcaba la fila,
-- sin nada recuperable detrás. Ahora un DELETE normal mueve el objeto a la
-- papelera de quien lo borró (deleted_at + deleted_by), sin tocar bytes ni
-- versiones; sólo /purge hace el borrado real e irreversible.
ALTER TABLE storage_objects ADD COLUMN deleted_by text;
