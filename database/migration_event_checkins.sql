-- Tabla para registros de asistencia por formulario QR (sin login).
-- Evita duplicados por evento + email.
CREATE TABLE IF NOT EXISTS event_checkins (
    id SERIAL PRIMARY KEY,
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    names VARCHAR(300) NOT NULL,
    email VARCHAR(200),
    cedula VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_event_checkins_event ON event_checkins(event_id);
CREATE INDEX IF NOT EXISTS idx_event_checkins_email ON event_checkins(event_id, email) WHERE email IS NOT NULL AND email != '';
CREATE UNIQUE INDEX IF NOT EXISTS idx_event_checkins_unique_email ON event_checkins(event_id, LOWER(email)) WHERE email IS NOT NULL AND email != '';

-- Duplicados por cedula en el mismo evento (opcional)
CREATE UNIQUE INDEX IF NOT EXISTS idx_event_checkins_unique_cedula ON event_checkins(event_id, cedula) WHERE cedula IS NOT NULL AND cedula != '';
