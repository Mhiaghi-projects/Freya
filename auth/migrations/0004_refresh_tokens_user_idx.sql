-- Índice sobre la FK refresh_tokens.user_id: Postgres no lo crea solo al
-- declarar REFERENCES (a diferencia del lado referenciado, que sí lo
-- indexa por ser PRIMARY KEY). Sin él, cada DELETE de un usuario
-- (delete_user hace borrado duro de verdad, docs/DECISIONS.md) obliga a
-- Postgres a recorrer TODA la tabla para encontrar las filas a las que
-- aplicar el ON DELETE CASCADE -- y refresh_tokens crece con cada
-- rotación de sesión (una fila nueva por refresh), no es una tabla que
-- se quede pequeña.

CREATE INDEX refresh_tokens_user_idx ON refresh_tokens (user_id);
