# Database initialization script
CREATE DATABASE IF NOT EXISTS chatico_mapper;
CREATE USER IF NOT EXISTS chatico_user WITH PASSWORD 'chatico_password';
GRANT ALL PRIVILEGES ON DATABASE chatico_mapper TO chatico_user;
