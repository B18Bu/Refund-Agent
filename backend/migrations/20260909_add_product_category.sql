ALTER TABLE products ADD COLUMN IF NOT EXISTS category VARCHAR(16) NOT NULL DEFAULT 'OTHER';
CREATE INDEX IF NOT EXISTS ix_products_category ON products (category);
