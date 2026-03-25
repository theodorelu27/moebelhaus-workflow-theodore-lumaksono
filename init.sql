CREATE TABLE IF NOT EXISTS customer_contacts (
  id              SERIAL PRIMARY KEY,
  channel         VARCHAR(20) NOT NULL,
  contact_name    VARCHAR(255),
  content         TEXT,
  summary         TEXT,
  sentiment       VARCHAR(20),
  has_todo        BOOLEAN DEFAULT false,
  is_critical     BOOLEAN DEFAULT false,
  received_at     TIMESTAMPTZ,
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  raw             JSONB
);

CREATE INDEX IF NOT EXISTS idx_sentiment ON customer_contacts(sentiment);
CREATE INDEX IF NOT EXISTS idx_is_critical ON customer_contacts(is_critical);
CREATE INDEX IF NOT EXISTS idx_channel ON customer_contacts(channel);
CREATE INDEX IF NOT EXISTS idx_received_at ON customer_contacts(received_at DESC);
