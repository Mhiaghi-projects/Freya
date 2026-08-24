-- Registro de tenants (proyectos): hoy un tenant era sólo "lo que sea que
-- alguien mande en X-Tenant-Context", sin ningún sitio que supiera cuáles
-- existen (docs/DECISIONS.md, brecha ya señalada). Vive en el schema de la
-- propia Freya (tenant "freya" es el plano de control) -- auth ya opera
-- ahí siempre que actúa el panel de administración.
CREATE TABLE tenants (
    id text PRIMARY KEY,
    name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by text
);

INSERT INTO tenants (id, name, created_by)
VALUES ('freya', 'Freya', NULL)
ON CONFLICT (id) DO NOTHING;
