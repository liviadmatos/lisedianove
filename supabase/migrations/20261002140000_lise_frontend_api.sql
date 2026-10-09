-- Extensões aditivas para frontend estático + API Flask separada.
-- Preserva contas, termos, radicais, turmas, trilhas e partidas existentes.
BEGIN;

ALTER TABLE public.usuarios
    ADD COLUMN IF NOT EXISTS ultimo_acesso_em TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS public.lise_colecoes (
    id SERIAL PRIMARY KEY,
    fk_usuario UUID NOT NULL REFERENCES public.usuarios(id_usuario) ON DELETE CASCADE,
    nome VARCHAR(100) NOT NULL,
    criada_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_lise_colecoes_fk_usuario ON public.lise_colecoes(fk_usuario);

CREATE TABLE IF NOT EXISTS public.lise_colecao_termos (
    id SERIAL PRIMARY KEY,
    fk_colecao INTEGER NOT NULL REFERENCES public.lise_colecoes(id) ON DELETE CASCADE,
    fk_termo INTEGER NOT NULL REFERENCES public.termos(id_termo) ON DELETE CASCADE,
    CONSTRAINT uq_lise_colecao_termos UNIQUE (fk_colecao, fk_termo)
);
CREATE INDEX IF NOT EXISTS ix_lise_colecao_termos_fk_colecao ON public.lise_colecao_termos(fk_colecao);
CREATE INDEX IF NOT EXISTS ix_lise_colecao_termos_fk_termo ON public.lise_colecao_termos(fk_termo);

CREATE TABLE IF NOT EXISTS public.lise_favoritos_termos (
    id SERIAL PRIMARY KEY,
    fk_usuario UUID NOT NULL REFERENCES public.usuarios(id_usuario) ON DELETE CASCADE,
    fk_termo INTEGER NOT NULL REFERENCES public.termos(id_termo) ON DELETE CASCADE,
    CONSTRAINT uq_lise_favoritos_termos UNIQUE (fk_usuario, fk_termo)
);
CREATE INDEX IF NOT EXISTS ix_lise_favoritos_termos_fk_usuario ON public.lise_favoritos_termos(fk_usuario);
CREATE INDEX IF NOT EXISTS ix_lise_favoritos_termos_fk_termo ON public.lise_favoritos_termos(fk_termo);

CREATE TABLE IF NOT EXISTS public.lise_favoritos_radicais (
    id SERIAL PRIMARY KEY,
    fk_usuario UUID NOT NULL REFERENCES public.usuarios(id_usuario) ON DELETE CASCADE,
    fk_radical INTEGER NOT NULL REFERENCES public.radicais(id_radical) ON DELETE CASCADE,
    CONSTRAINT uq_lise_favoritos_radicais UNIQUE (fk_usuario, fk_radical)
);
CREATE INDEX IF NOT EXISTS ix_lise_favoritos_radicais_fk_usuario ON public.lise_favoritos_radicais(fk_usuario);
CREATE INDEX IF NOT EXISTS ix_lise_favoritos_radicais_fk_radical ON public.lise_favoritos_radicais(fk_radical);

CREATE TABLE IF NOT EXISTS public.lise_game_sessions (
    id VARCHAR(36) PRIMARY KEY,
    fk_usuario UUID NOT NULL REFERENCES public.usuarios(id_usuario) ON DELETE CASCADE,
    fk_turma INTEGER REFERENCES public.turmas(id_turma) ON DELETE CASCADE,
    fk_turma_trilha INTEGER REFERENCES public.turma_trilha(id) ON DELETE SET NULL,
    jogo VARCHAR(24) NOT NULL,
    source_type VARCHAR(24) NOT NULL,
    source_id INTEGER,
    total INTEGER NOT NULL DEFAULT 0,
    corretas INTEGER NOT NULL DEFAULT 0,
    xp INTEGER NOT NULL DEFAULT 0,
    pontuacao INTEGER NOT NULL DEFAULT 0,
    criada_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finalizada_em TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_lise_game_sessions_fk_usuario ON public.lise_game_sessions(fk_usuario);
CREATE INDEX IF NOT EXISTS ix_lise_game_sessions_fk_turma ON public.lise_game_sessions(fk_turma);
CREATE INDEX IF NOT EXISTS ix_lise_game_sessions_fk_turma_trilha ON public.lise_game_sessions(fk_turma_trilha);
CREATE INDEX IF NOT EXISTS ix_lise_game_sessions_class_date ON public.lise_game_sessions(fk_turma, finalizada_em);

CREATE TABLE IF NOT EXISTS public.lise_game_session_questions (
    id SERIAL PRIMARY KEY,
    fk_sessao VARCHAR(36) NOT NULL REFERENCES public.lise_game_sessions(id) ON DELETE CASCADE,
    fk_partida VARCHAR(36) NOT NULL UNIQUE REFERENCES public.lise_partidas(id) ON DELETE CASCADE,
    posicao INTEGER NOT NULL,
    payload JSONB NOT NULL,
    CONSTRAINT uq_lise_game_session_question_position UNIQUE (fk_sessao, posicao)
);
CREATE INDEX IF NOT EXISTS ix_lise_game_session_questions_fk_sessao ON public.lise_game_session_questions(fk_sessao);

-- A API conecta ao PostgreSQL no servidor. O navegador não ganha acesso direto.
DO $$
DECLARE table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'lise_colecoes', 'lise_colecao_termos', 'lise_favoritos_termos',
        'lise_favoritos_radicais', 'lise_game_sessions', 'lise_game_session_questions'
    ] LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('REVOKE ALL ON TABLE public.%I FROM PUBLIC, anon, authenticated', table_name);
    END LOOP;
END $$;

REVOKE ALL ON SEQUENCE public.lise_colecoes_id_seq FROM PUBLIC, anon, authenticated;
REVOKE ALL ON SEQUENCE public.lise_colecao_termos_id_seq FROM PUBLIC, anon, authenticated;
REVOKE ALL ON SEQUENCE public.lise_favoritos_termos_id_seq FROM PUBLIC, anon, authenticated;
REVOKE ALL ON SEQUENCE public.lise_favoritos_radicais_id_seq FROM PUBLIC, anon, authenticated;
REVOKE ALL ON SEQUENCE public.lise_game_session_questions_id_seq FROM PUBLIC, anon, authenticated;

COMMIT;
