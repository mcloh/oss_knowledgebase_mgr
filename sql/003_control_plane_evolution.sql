-- Evolução idempotente para instalações criadas antes do onboarding e SMTP.
CREATE TABLE IF NOT EXISTS activation_tokens (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash text NOT NULL UNIQUE,
  expires_at timestamptz NOT NULL,
  used_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS system_settings (
  setting_key text PRIMARY KEY,
  value_ciphertext bytea NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS webhook_secret_ciphertext bytea;
