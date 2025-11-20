# Database initialization script (PostgreSQL)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT FROM pg_catalog.pg_roles WHERE rolname = 'chatico_user'
    ) THEN
        CREATE ROLE chatico_user LOGIN PASSWORD 'chatico_password';
    END IF;
END
$$;

SELECT 'CREATE DATABASE chatico_mapper WITH OWNER chatico_user'
WHERE NOT EXISTS (
    SELECT FROM pg_database WHERE datname = 'chatico_mapper'
)\gexec

GRANT ALL PRIVILEGES ON DATABASE chatico_mapper TO chatico_user;
