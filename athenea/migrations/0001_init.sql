-- Esquema de athenea: páginas, bloques y adjuntos (metadatos únicamente --
-- los bytes de un adjunto viven en storage, subidos por el cliente a través
-- del gateway de frontend, nunca por este servicio).

CREATE TABLE athenea_pages (
    id text PRIMARY KEY,
    title text NOT NULL,
    parent_id text REFERENCES athenea_pages (id) ON DELETE CASCADE,
    owner_user_id text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz
);

CREATE INDEX athenea_pages_owner_idx ON athenea_pages (owner_user_id)
    WHERE deleted_at IS NULL;

CREATE TABLE athenea_blocks (
    id text PRIMARY KEY,
    page_id text NOT NULL REFERENCES athenea_pages (id) ON DELETE CASCADE,
    block_type text NOT NULL,
    content text NOT NULL DEFAULT '',
    position int NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX athenea_blocks_page_idx ON athenea_blocks (page_id, position);

CREATE TABLE athenea_attachments (
    id text PRIMARY KEY,
    page_id text NOT NULL REFERENCES athenea_pages (id) ON DELETE CASCADE,
    bucket text NOT NULL,
    object_key text NOT NULL,
    filename text NOT NULL,
    content_type text NOT NULL,
    uploaded_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX athenea_attachments_page_idx ON athenea_attachments (page_id);
