-- Script para agregar 'cancelled' al CHECK constraint del campo status en la tabla events
-- Ejecutar este script en el SQL Editor de Supabase

-- Paso 1: Eliminar el constraint existente
ALTER TABLE events 
DROP CONSTRAINT IF EXISTS events_status_check;

-- Paso 2: Agregar el nuevo constraint con 'cancelled' incluido
ALTER TABLE events 
ADD CONSTRAINT events_status_check 
CHECK (status IN ('pending', 'approved', 'denied', 'finalized', 'cancelled'));
