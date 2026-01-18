-- Migration: Create hush_rank_rewards table
-- Date: 2026-01-18
-- Description: HUSH coin rewards for each rank (replaces old bonus codes)

CREATE TABLE IF NOT EXISTS hush_rank_rewards (
    id SERIAL PRIMARY KEY,
    rank_id INT NOT NULL REFERENCES ranks(id) ON DELETE CASCADE,
    reward_amount INT NOT NULL,
    position INT NOT NULL CHECK (position BETWEEN 1 AND 3),
    UNIQUE (rank_id, position)
);

-- Insert HUSH rewards for each rank
-- Rookie (id=1): No rewards (0)
INSERT INTO hush_rank_rewards (rank_id, reward_amount, position) VALUES
    (1, 0, 1), (1, 0, 2), (1, 0, 3)
ON CONFLICT (rank_id, position) DO UPDATE SET reward_amount = EXCLUDED.reward_amount;

-- Hustler (id=2): [100, 150, 250]
INSERT INTO hush_rank_rewards (rank_id, reward_amount, position) VALUES
    (2, 100, 1), (2, 150, 2), (2, 250, 3)
ON CONFLICT (rank_id, position) DO UPDATE SET reward_amount = EXCLUDED.reward_amount;

-- Closer (id=3): [400, 750, 1000]
INSERT INTO hush_rank_rewards (rank_id, reward_amount, position) VALUES
    (3, 400, 1), (3, 750, 2), (3, 1000, 3)
ON CONFLICT (rank_id, position) DO UPDATE SET reward_amount = EXCLUDED.reward_amount;

-- Shark (id=4): [750, 1000, 1500]
INSERT INTO hush_rank_rewards (rank_id, reward_amount, position) VALUES
    (4, 750, 1), (4, 1000, 2), (4, 1500, 3)
ON CONFLICT (rank_id, position) DO UPDATE SET reward_amount = EXCLUDED.reward_amount;

-- King of Greed (id=5): [1000, 1500, 2000]
INSERT INTO hush_rank_rewards (rank_id, reward_amount, position) VALUES
    (5, 1000, 1), (5, 1500, 2), (5, 2000, 3)
ON CONFLICT (rank_id, position) DO UPDATE SET reward_amount = EXCLUDED.reward_amount;

-- Chatting God (id=6): [1500, 2500, 5000]
INSERT INTO hush_rank_rewards (rank_id, reward_amount, position) VALUES
    (6, 1500, 1), (6, 2500, 2), (6, 5000, 3)
ON CONFLICT (rank_id, position) DO UPDATE SET reward_amount = EXCLUDED.reward_amount;

-- Verify
SELECT r.name, hrr.reward_amount, hrr.position
FROM hush_rank_rewards hrr
JOIN ranks r ON r.id = hrr.rank_id
ORDER BY r.display_order, hrr.position;
