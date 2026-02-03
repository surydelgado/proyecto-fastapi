-- Tabla de usuarios
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    names VARCHAR(200) NOT NULL,
    surnames VARCHAR(200) NOT NULL,
    cedula VARCHAR(20) NOT NULL DEFAULT '',
    email VARCHAR(200) UNIQUE NOT NULL,
    role VARCHAR(20) DEFAULT 'externo' CHECK (role IN ('admin', 'teacher', 'student', 'interno', 'externo')),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Tabla de eventos
CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    event_type VARCHAR(100),
    audience VARCHAR(30) DEFAULT 'publico' CHECK (audience IN ('interno', 'interuniversitario', 'publico')),
    allowed_domains JSONB,
    allowed_emails JSONB,
    access_note TEXT,
    cover_image_url TEXT,
    requires_certificate BOOLEAN DEFAULT FALSE,
    certificate_template VARCHAR(100) DEFAULT 'default',
    certificate_title VARCHAR(200),
    certificate_signer_name VARCHAR(200),
    certificate_signer_role VARCHAR(200),
    certificate_signer_image_url TEXT,
    requires_professor_signature BOOLEAN DEFAULT FALSE,
    certificate_professor_signer_name VARCHAR(200),
    certificate_professor_signer_role VARCHAR(200),
    certificate_professor_signer_image_url TEXT,
    certificate_background_url TEXT,
    start_date TIMESTAMPTZ NOT NULL,
    end_date TIMESTAMPTZ NOT NULL,
    location VARCHAR(150),
    capacity INTEGER CHECK (capacity > 0),
    status VARCHAR(30) DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'denied', 'finalized')),
    is_active BOOLEAN DEFAULT TRUE,
    creator_id UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Tabla de asistencias
CREATE TABLE IF NOT EXISTS attendances (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    qr_code VARCHAR(255) UNIQUE NOT NULL,
    attended BOOLEAN DEFAULT FALSE,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, event_id)
);

-- Tabla de credenciales/microcredenciales
CREATE TABLE IF NOT EXISTS credentials (
    id SERIAL PRIMARY KEY,
    credential_code VARCHAR(100) UNIQUE NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    issued_at TIMESTAMPTZ DEFAULT NOW(),
    is_valid BOOLEAN DEFAULT TRUE,
    certificate_url TEXT
);

-- Tabla de notificaciones
CREATE TABLE IF NOT EXISTS notifications (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL,
    message TEXT,
    link_url TEXT,
    type VARCHAR(30) DEFAULT 'info',
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_events_creator ON events(creator_id);
CREATE INDEX IF NOT EXISTS idx_events_start_date ON events(start_date);
CREATE INDEX IF NOT EXISTS idx_events_status ON events(status);
CREATE INDEX IF NOT EXISTS idx_attendances_user ON attendances(user_id);
CREATE INDEX IF NOT EXISTS idx_attendances_event ON attendances(event_id);
CREATE INDEX IF NOT EXISTS idx_attendances_qr ON attendances(qr_code);
CREATE INDEX IF NOT EXISTS idx_credentials_user ON credentials(user_id);
CREATE INDEX IF NOT EXISTS idx_credentials_event ON credentials(event_id);
CREATE INDEX IF NOT EXISTS idx_credentials_code ON credentials(credential_code);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(is_read);
CREATE INDEX IF NOT EXISTS idx_notifications_created_at ON notifications(created_at);

-- Row Level Security
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE events ENABLE ROW LEVEL SECURITY;
ALTER TABLE attendances ENABLE ROW LEVEL SECURITY;
ALTER TABLE credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;

-- Políticas RLS
CREATE POLICY "Users can view own profile" ON users
    FOR SELECT USING (auth.uid() = id);

CREATE POLICY "Anyone can view active events" ON events
    FOR SELECT USING (is_active = TRUE);

CREATE POLICY "Authenticated users can create events" ON events
    FOR INSERT WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "Creator or admin can update events" ON events
    FOR UPDATE USING (
        creator_id = auth.uid() OR 
        EXISTS (SELECT 1 FROM users WHERE id = auth.uid() AND role = 'admin')
    );

CREATE POLICY "Users can view own attendances" ON attendances
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can create own attendances" ON attendances
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can view own notifications" ON notifications
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can update own notifications" ON notifications
    FOR UPDATE USING (auth.uid() = user_id);
