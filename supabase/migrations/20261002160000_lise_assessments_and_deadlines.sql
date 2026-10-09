-- Extensões aditivas da reformulação LISE para Vercel.
-- Não remove nem altera os termos, radicais, turmas ou trilhas existentes.

ALTER TABLE public.turma_trilha
  ADD COLUMN IF NOT EXISTS data_limite date;

ALTER TABLE public.usuario_trilha_termo
  ADD COLUMN IF NOT EXISTS jogado boolean NOT NULL DEFAULT false;

-- Preserva o progresso antigo de acertos e considera partidas antigas respondidas
-- como prática, sem transformar o antigo BioQuiz em jogo/prática.
UPDATE public.usuario_trilha_termo
SET jogado = true
WHERE acertou IS TRUE AND jogado IS FALSE;

INSERT INTO public.usuario_trilha_termo AS progress
  (fk_usuario, fk_turma_trilha, fk_termo, acertou, data_conclusao, jogado)
SELECT fk_usuario, fk_turma_trilha, fk_termo,
       bool_or(correto IS TRUE), min(respondida_em), true
FROM public.lise_partidas
WHERE fk_turma_trilha IS NOT NULL
  AND respondida IS TRUE
  AND jogo <> 'bioquiz'
GROUP BY fk_usuario, fk_turma_trilha, fk_termo
ON CONFLICT (fk_usuario, fk_turma_trilha, fk_termo) DO UPDATE SET
  acertou = COALESCE(progress.acertou, false) OR COALESCE(EXCLUDED.acertou, false),
  data_conclusao = COALESCE(progress.data_conclusao, EXCLUDED.data_conclusao),
  jogado = true;

CREATE TABLE IF NOT EXISTS public.lise_avaliacoes (
  id bigserial PRIMARY KEY,
  fk_turma_trilha integer NOT NULL UNIQUE
    REFERENCES public.turma_trilha(id) ON DELETE CASCADE,
  titulo varchar(150) NOT NULL,
  quantidade integer NOT NULL DEFAULT 10 CHECK (quantidade BETWEEN 1 AND 50),
  conteudo varchar(16) NOT NULL DEFAULT 'ambos'
    CHECK (conteudo IN ('termos', 'radicais', 'ambos')),
  formato varchar(32) NOT NULL DEFAULT 'misto'
    CHECK (formato IN ('misto', 'termo_definicao', 'definicao_termo', 'radical_significado', 'significado_radical')),
  nota_minima integer NOT NULL DEFAULT 70 CHECK (nota_minima BETWEEN 0 AND 100),
  fk_professor uuid NOT NULL REFERENCES public.usuarios(id_usuario) ON DELETE CASCADE,
  criada_em timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.lise_avaliacao_sessoes (
  id varchar(36) PRIMARY KEY,
  fk_avaliacao bigint NOT NULL REFERENCES public.lise_avaliacoes(id) ON DELETE CASCADE,
  fk_usuario uuid NOT NULL REFERENCES public.usuarios(id_usuario) ON DELETE CASCADE,
  total integer NOT NULL DEFAULT 0 CHECK (total >= 0),
  corretas integer NOT NULL DEFAULT 0 CHECK (corretas >= 0),
  pontuacao integer NOT NULL DEFAULT 0 CHECK (pontuacao BETWEEN 0 AND 100),
  nota_minima integer NOT NULL DEFAULT 70 CHECK (nota_minima BETWEEN 0 AND 100),
  aprovada boolean NOT NULL DEFAULT false,
  criada_em timestamptz NOT NULL DEFAULT now(),
  finalizada_em timestamptz
);

CREATE TABLE IF NOT EXISTS public.lise_avaliacao_questoes (
  id varchar(36) PRIMARY KEY,
  fk_sessao varchar(36) NOT NULL
    REFERENCES public.lise_avaliacao_sessoes(id) ON DELETE CASCADE,
  posicao integer NOT NULL CHECK (posicao > 0),
  fk_termo integer REFERENCES public.termos(id_termo) ON DELETE SET NULL,
  fk_radical integer REFERENCES public.radicais(id_radical) ON DELETE SET NULL,
  prompt text NOT NULL,
  opcoes jsonb NOT NULL,
  resposta_esperada varchar(80) NOT NULL,
  respondida boolean NOT NULL DEFAULT false,
  correta boolean,
  UNIQUE (fk_sessao, posicao)
);

CREATE INDEX IF NOT EXISTS ix_lise_avaliacoes_assignment
  ON public.lise_avaliacoes (fk_turma_trilha);
CREATE INDEX IF NOT EXISTS ix_lise_avaliacao_sessoes_user_date
  ON public.lise_avaliacao_sessoes (fk_usuario, finalizada_em DESC);
CREATE INDEX IF NOT EXISTS ix_lise_avaliacao_sessoes_exam_date
  ON public.lise_avaliacao_sessoes (fk_avaliacao, finalizada_em DESC);
CREATE INDEX IF NOT EXISTS ix_lise_avaliacao_questoes_session
  ON public.lise_avaliacao_questoes (fk_sessao, posicao);
CREATE INDEX IF NOT EXISTS ix_lise_progress_user_assignment_terms_played
  ON public.usuario_trilha_termo (fk_usuario, fk_turma_trilha, fk_termo)
  WHERE jogado IS TRUE;
CREATE INDEX IF NOT EXISTS ix_lise_assessment_sessions_user_exam_date
  ON public.lise_avaliacao_sessoes (fk_usuario, fk_avaliacao, finalizada_em DESC);

ALTER TABLE public.lise_avaliacoes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lise_avaliacao_sessoes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lise_avaliacao_questoes ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.lise_avaliacoes FROM anon, authenticated;
REVOKE ALL ON TABLE public.lise_avaliacao_sessoes FROM anon, authenticated;
REVOKE ALL ON TABLE public.lise_avaliacao_questoes FROM anon, authenticated;
REVOKE ALL ON SEQUENCE public.lise_avaliacoes_id_seq FROM anon, authenticated;

GRANT ALL ON TABLE public.lise_avaliacoes TO service_role;
GRANT ALL ON TABLE public.lise_avaliacao_sessoes TO service_role;
GRANT ALL ON TABLE public.lise_avaliacao_questoes TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.lise_avaliacoes_id_seq TO service_role;
