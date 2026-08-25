-- Leaderboard semanal (pedido explícito del usuario: "resetear el nivel
-- cada semana y ponerlo en el leaderboard"). total_xp/level (0001_init)
-- se quedan como el progreso de siempre (logros, streak) -- weekly_xp es
-- aparte, lo que compite semana a semana, y se resetea sin tocar lo demás.

ALTER TABLE gam_user_stats ADD COLUMN weekly_xp bigint NOT NULL DEFAULT 0;
ALTER TABLE gam_user_stats ADD COLUMN weekly_coins bigint NOT NULL DEFAULT 0;

-- Foto del ranking de cada semana justo antes de resetear -- si no,
-- "quién ganó esta semana" se perdería en el instante mismo del reset.
CREATE TABLE gam_weekly_leaderboard_snapshots (
    id text PRIMARY KEY,
    week_start date NOT NULL,
    user_id text NOT NULL,
    weekly_xp bigint NOT NULL,
    rank int NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX gam_weekly_snapshots_week_idx
    ON gam_weekly_leaderboard_snapshots (week_start, rank);

-- Fila única: qué semana (lunes) fue la última en resetearse -- así el
-- poll periódico (WeeklyResetter) sabe si ya tocó o no sin depender de
-- que el propio proceso siga vivo entre reinicios.
CREATE TABLE gam_weekly_reset_state (
    id text PRIMARY KEY DEFAULT 'singleton',
    last_reset_week_start date
);
