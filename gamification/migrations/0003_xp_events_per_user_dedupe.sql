-- Pedido explícito del usuario: cuando una task del backlog llega a
-- "done", TODOS los usuarios del proyecto reciben xp y monedas, no sólo
-- quien la completó. La deduplicación (source, source_ref) sólo dejaba
-- una fila por task -- ahora hace falta una por (task, usuario) para que
-- cada miembro del equipo tenga su propio evento sin bloquear a los demás.
DROP INDEX gam_xp_events_dedupe_idx;
CREATE UNIQUE INDEX gam_xp_events_dedupe_idx
    ON gam_xp_events (source, source_ref, user_id);
