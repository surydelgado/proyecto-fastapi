-- Schema SQL para Supabase
-- Ejecutar estos comandos en el SQL Editor de Supabase

-- Tabla de usuarios (complementa la tabla auth.users de Supabase)
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
    start_date TIMESTAMPTZ NOT NULL,
    end_date TIMESTAMPTZ NOT NULL,
    location VARCHAR(150),
    capacity INTEGER CHECK (capacity > 0),
    status VARCHAR(30) DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'denied')),
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
    is_valid BOOLEAN DEFAULT TRUE
);

-- Índices para mejorar el rendimiento
CREATE INDEX IF NOT EXISTS idx_events_creator ON events(creator_id);
CREATE INDEX IF NOT EXISTS idx_events_start_date ON events(start_date);
CREATE INDEX IF NOT EXISTS idx_events_status ON events(status);
CREATE INDEX IF NOT EXISTS idx_attendances_user ON attendances(user_id);
CREATE INDEX IF NOT EXISTS idx_attendances_event ON attendances(event_id);
CREATE INDEX IF NOT EXISTS idx_attendances_qr ON attendances(qr_code);
CREATE INDEX IF NOT EXISTS idx_credentials_user ON credentials(user_id);
CREATE INDEX IF NOT EXISTS idx_credentials_event ON credentials(event_id);
CREATE INDEX IF NOT EXISTS idx_credentials_code ON credentials(credential_code);

-- Habilitar Row Level Security (RLS)
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE events ENABLE ROW LEVEL SECURITY;
ALTER TABLE attendances ENABLE ROW LEVEL SECURITY;
ALTER TABLE credentials ENABLE ROW LEVEL SECURITY;

-- Políticas básicas de RLS (ajustar según necesidades de seguridad)
-- Política para usuarios: pueden ver su propia información
CREATE POLICY "Users can view own profile" ON users
    FOR SELECT USING (auth.uid() = id);

-- Política para eventos: todos pueden ver eventos activos
CREATE POLICY "Anyone can view active events" ON events
    FOR SELECT USING (is_active = TRUE);

-- Política para eventos: usuarios autenticados pueden crear eventos
CREATE POLICY "Authenticated users can create events" ON events
    FOR INSERT WITH CHECK (auth.role() = 'authenticated');

-- Política para eventos: solo el creador o admin puede actualizar
CREATE POLICY "Creator or admin can update events" ON events
    FOR UPDATE USING (
        creator_id = auth.uid() OR 
        EXISTS (SELECT 1 FROM users WHERE id = auth.uid() AND role = 'admin')
    );

-- Política para asistencias: usuarios pueden ver sus propias asistencias
CREATE POLICY "Users can view own attendances" ON attendances
    FOR SELECT USING (auth.uid() = user_id);

-- Política para asistencias: usuarios pueden crear sus propias asistencias
CREATE POLICY "Users can create own attendances" ON attendances
    FOR INSERT WITH CHECK (auth.uid() = user_id);

-- Nota: Ajustar estas políticas según los requisitos específicos de seguridad de la institución.

-- IMPORTANTE: Configurar Supabase Auth para requerir verificación de email
-- Esto se hace en la configuración de Supabase Dashboard:
-- Authentication > Settings > Email Auth > Enable email confirmations
