-- Migration: Update rank thresholds and emojis
-- Date: 2026-01-18
-- Description: Update sales thresholds for HUSH coin bonus system

-- New thresholds:
-- Rookie: $0 – $1,999
-- Hustler: $2,000 – $6,999
-- Closer: $7,000 – $11,999
-- Shark: $12,000 – $17,999
-- King of Greed: $18,000 – $29,999
-- Chatting God: $30,000+

UPDATE ranks SET min_amount = 0, max_amount = 1999.99 WHERE name = 'Rookie';
UPDATE ranks SET min_amount = 2000, max_amount = 6999.99 WHERE name = 'Hustler';
UPDATE ranks SET min_amount = 7000, max_amount = 11999.99 WHERE name = 'Closer';
UPDATE ranks SET min_amount = 12000, max_amount = 17999.99 WHERE name = 'Shark';
UPDATE ranks SET min_amount = 18000, max_amount = 29999.99 WHERE name = 'King of Greed';
UPDATE ranks SET min_amount = 30000, max_amount = 999999.99 WHERE name = 'Chatting God';

-- Verify
SELECT id, name, min_amount, max_amount, emoji
FROM ranks
ORDER BY display_order;
