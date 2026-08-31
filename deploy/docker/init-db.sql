-- Tách CSDL theo dịch vụ: sự cố ở một dịch vụ không kéo theo dịch vụ khác.
CREATE DATABASE n8n;
CREATE DATABASE fleet_checkpoints;

-- Tài khoản CHỈ ĐỌC cho agent phân tích.
-- Quan trọng: quyền chỉ đọc phải cưỡng chế ở TẦNG CSDL, không phải ở cấu hình
-- hay ở prompt. Cấu hình sai được, prompt bị dẫn dụ được; GRANT thì không.
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'fleet_readonly') THEN
    CREATE ROLE fleet_readonly LOGIN PASSWORD 'CHANGE_ME_IN_PROD';
  END IF;
END $$;

REVOKE ALL ON DATABASE fleet FROM fleet_readonly;
GRANT CONNECT ON DATABASE fleet TO fleet_readonly;
