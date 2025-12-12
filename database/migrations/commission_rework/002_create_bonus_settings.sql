-- Migration: Create bonus_settings table
-- Version: 002
-- Date: 2025-12-12
-- Description: Settings for bonus calculations (bonus_counter_percentage etc.)

CREATE TABLE IF NOT EXISTS bonus_settings (
    id SERIAL PRIMARY KEY,
    setting_key VARCHAR(50) UNIQUE NOT NULL,
    setting_value DECIMAL(10,4) NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

-- Create index
CREATE INDEX IF NOT EXISTS idx_bonus_settings_key
ON bonus_settings(setting_key) WHERE is_active = TRUE;

-- Insert initial settings
INSERT INTO bonus_settings (setting_key, setting_value, description)
VALUES
    ('bonus_counter_percentage', 0.01, 'Bonus percentage for bonus_counter=true (1%)')
ON CONFLICT (setting_key) DO NOTHING;

-- Function to get bonus setting
CREATE OR REPLACE FUNCTION get_bonus_setting(key_name VARCHAR)
RETURNS DECIMAL AS $$
DECLARE
    result DECIMAL;
BEGIN
    SELECT setting_value INTO result
    FROM bonus_settings
    WHERE setting_key = key_name AND is_active = TRUE
    LIMIT 1;

    RETURN COALESCE(result, 0);
END;
$$ LANGUAGE plpgsql;

COMMENT ON TABLE bonus_settings IS 'System settings for bonus calculations';
COMMENT ON FUNCTION get_bonus_setting(VARCHAR) IS 'Get bonus setting value by key';
