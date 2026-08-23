-- El contenido cifrado deja de vivir embebido en la fila: gestor-db sólo
-- guarda dónde está (una clave de storage), igual que storage hace con
-- sus propios objetos (bytes fuera de la base, metadatos dentro). El
-- valor sigue viajando cifrado -- storage nunca ve el DEK ni la master
-- key, sólo un blob opaco -- así que mover el ciphertext ahí no reduce la
-- protección; sólo saca de gestor-db algo que puede crecer sin límite
-- (una clave RSA, y en el futuro certificados más grandes).
ALTER TABLE secret_versions RENAME COLUMN value_ciphertext TO value_storage_key;
