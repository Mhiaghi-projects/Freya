-- Esquema de gamification (docs/ROADMAP.md Fase 10). user_id no lleva FK a
-- ninguna tabla de auth -- gamification nunca ve gestor-db de auth, sólo
-- conoce el id que viene en el JWT (mismo principio que el resto de la
-- plataforma: cada servicio confía en el token, no en una FK cruzada).

CREATE TABLE gam_user_stats (
    user_id text PRIMARY KEY,
    total_xp bigint NOT NULL DEFAULT 0,
    level int NOT NULL DEFAULT 1,
    coins bigint NOT NULL DEFAULT 0,
    current_streak int NOT NULL DEFAULT 0,
    longest_streak int NOT NULL DEFAULT 0,
    last_activity_date date,
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- source+source_ref es la clave de deduplicación real: procesar la misma
-- task completada dos veces (el sync vuelve a listarla en el próximo ciclo
-- hasta que quede registrada aquí) no debe otorgar XP dos veces.
CREATE TABLE gam_xp_events (
    id text PRIMARY KEY,
    user_id text NOT NULL,
    source text NOT NULL,
    source_ref text NOT NULL,
    xp int NOT NULL,
    coins int NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX gam_xp_events_dedupe_idx ON gam_xp_events (source, source_ref);
CREATE INDEX gam_xp_events_user_idx ON gam_xp_events (user_id, created_at);

CREATE TABLE gam_achievements (
    code text PRIMARY KEY,
    name text NOT NULL,
    description text NOT NULL DEFAULT '',
    icon text NOT NULL DEFAULT '🏆'
);

CREATE TABLE gam_achievement_unlocks (
    id text PRIMARY KEY,
    user_id text NOT NULL,
    achievement_code text NOT NULL REFERENCES gam_achievements (code),
    unlocked_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX gam_unlocks_dedupe_idx
    ON gam_achievement_unlocks (user_id, achievement_code);

CREATE TABLE gam_habits (
    id text PRIMARY KEY,
    user_id text NOT NULL,
    name text NOT NULL,
    frequency text NOT NULL DEFAULT 'daily',
    created_at timestamptz NOT NULL DEFAULT now(),
    archived_at timestamptz
);
CREATE INDEX gam_habits_user_idx ON gam_habits (user_id);

CREATE TABLE gam_habit_logs (
    id text PRIMARY KEY,
    habit_id text NOT NULL REFERENCES gam_habits (id) ON DELETE CASCADE,
    logged_date date NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX gam_habit_logs_dedupe_idx ON gam_habit_logs (habit_id, logged_date);

CREATE TABLE gam_rewards (
    id text PRIMARY KEY,
    user_id text NOT NULL,
    name text NOT NULL,
    coin_cost int NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    archived_at timestamptz
);
CREATE INDEX gam_rewards_user_idx ON gam_rewards (user_id);

CREATE TABLE gam_reward_redemptions (
    id text PRIMARY KEY,
    reward_id text NOT NULL REFERENCES gam_rewards (id),
    user_id text NOT NULL,
    coin_cost int NOT NULL,
    redeemed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE gam_goals (
    id text PRIMARY KEY,
    user_id text NOT NULL,
    period text NOT NULL,
    target_type text NOT NULL,
    target_value int NOT NULL,
    period_start date NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    archived_at timestamptz
);
CREATE INDEX gam_goals_user_idx ON gam_goals (user_id);
