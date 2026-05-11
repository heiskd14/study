-- ==========================================
-- NexAuth — MySQL Database Setup Script
-- Run this once before starting the backend
-- ==========================================

-- Create the database
CREATE DATABASE IF NOT EXISTS nexauth
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE nexauth;

-- Create the users table
CREATE TABLE IF NOT EXISTS users (
  id          INT             NOT NULL AUTO_INCREMENT,
  name        VARCHAR(100)    NOT NULL,
  email       VARCHAR(255)    NOT NULL,
  password    VARCHAR(255)    NOT NULL,
  created_at  TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,

  PRIMARY KEY (id),
  UNIQUE KEY  uq_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Verify
DESCRIBE users;
SELECT 'NexAuth database and users table created ✅' AS status;
