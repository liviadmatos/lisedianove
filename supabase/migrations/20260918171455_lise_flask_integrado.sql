-- LISE: instalação nova ou atualização do banco(1).sql fornecido.
-- Aplicar UMA VEZ no SQL Editor do projeto de destino (como postgres).
-- Preserva linhas existentes. Faz a transição para acesso exclusivo pelo servidor Flask.
-- Revoga acesso direto às tabelas por anon/authenticated: não aplicar enquanto o
-- front/API anterior ainda depender desses acessos. Consulte README antes de executar.
BEGIN;


CREATE TABLE IF NOT EXISTS areas (
	id_area SERIAL NOT NULL, 
	nome VARCHAR(100) NOT NULL, 
	PRIMARY KEY (id_area), 
	UNIQUE (nome)
)

;


CREATE TABLE IF NOT EXISTS lise_limites_auth (
	chave VARCHAR(64) NOT NULL, 
	tentativas INTEGER NOT NULL, 
	inicio TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (chave)
)

;


CREATE TABLE IF NOT EXISTS usuarios (
	id_usuario UUID NOT NULL, 
	nome VARCHAR(150) NOT NULL, 
	email VARCHAR(255) NOT NULL, 
	perfil VARCHAR(20) NOT NULL, 
	criado_em TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id_usuario), 
	UNIQUE (email)
)

;


CREATE TABLE IF NOT EXISTS lise_conquistas (
	id SERIAL NOT NULL, 
	fk_usuario UUID NOT NULL, 
	codigo VARCHAR(30) NOT NULL, 
	criada_em TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (fk_usuario, codigo), 
	FOREIGN KEY(fk_usuario) REFERENCES usuarios (id_usuario) ON DELETE CASCADE
)

;


CREATE TABLE IF NOT EXISTS lise_sessoes (
	id VARCHAR(64) NOT NULL, 
	fk_usuario UUID NOT NULL, 
	expira_em TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(fk_usuario) REFERENCES usuarios (id_usuario) ON DELETE CASCADE
)

;


CREATE TABLE IF NOT EXISTS radicais (
	id_radical SERIAL NOT NULL, 
	nome VARCHAR(100) NOT NULL, 
	significado TEXT NOT NULL, 
	classificacao VARCHAR(20) NOT NULL, 
	fk_area INTEGER, 
	PRIMARY KEY (id_radical), 
	FOREIGN KEY(fk_area) REFERENCES areas (id_area)
)

;


CREATE TABLE IF NOT EXISTS termos (
	id_termo SERIAL NOT NULL, 
	palavra_completa VARCHAR(200) NOT NULL, 
	definicao_biologica TEXT NOT NULL, 
	fk_area INTEGER, 
	criado_por UUID, 
	criado_pelo_professor BOOLEAN, 
	criado_em TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id_termo), 
	FOREIGN KEY(fk_area) REFERENCES areas (id_area), 
	FOREIGN KEY(criado_por) REFERENCES usuarios (id_usuario)
)

;


CREATE TABLE IF NOT EXISTS trilhas (
	id_trilha SERIAL NOT NULL, 
	nome VARCHAR(150) NOT NULL, 
	fk_professor UUID NOT NULL, 
	criado_em TIMESTAMP WITH TIME ZONE, 
	descricao TEXT NOT NULL, 
	area VARCHAR(100) NOT NULL, 
	PRIMARY KEY (id_trilha), 
	FOREIGN KEY(fk_professor) REFERENCES usuarios (id_usuario)
)

;


CREATE TABLE IF NOT EXISTS turmas (
	id_turma SERIAL NOT NULL, 
	nome VARCHAR(150) NOT NULL, 
	codigo VARCHAR(6) NOT NULL, 
	fk_professor UUID NOT NULL, 
	criado_em TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id_turma), 
	UNIQUE (codigo), 
	FOREIGN KEY(fk_professor) REFERENCES usuarios (id_usuario)
)

;


CREATE TABLE IF NOT EXISTS flashcards (
	id_flashcard SERIAL NOT NULL, 
	fk_usuario UUID NOT NULL, 
	fk_termo INTEGER NOT NULL, 
	ativo BOOLEAN, 
	dificuldade VARCHAR(20), 
	proxima_revisao_em TIMESTAMP WITH TIME ZONE, 
	criado_em TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id_flashcard), 
	UNIQUE (fk_usuario, fk_termo), 
	FOREIGN KEY(fk_usuario) REFERENCES usuarios (id_usuario) ON DELETE CASCADE, 
	FOREIGN KEY(fk_termo) REFERENCES termos (id_termo) ON DELETE CASCADE
)

;


CREATE TABLE IF NOT EXISTS lise_recompensas (
	id SERIAL NOT NULL, 
	fk_usuario UUID NOT NULL, 
	fk_termo INTEGER NOT NULL, 
	jogo VARCHAR(20) NOT NULL, 
	dia DATE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (fk_usuario, fk_termo, jogo, dia), 
	FOREIGN KEY(fk_usuario) REFERENCES usuarios (id_usuario) ON DELETE CASCADE, 
	FOREIGN KEY(fk_termo) REFERENCES termos (id_termo) ON DELETE CASCADE
)

;


CREATE TABLE IF NOT EXISTS lise_termo_turmas (
	id SERIAL NOT NULL, 
	fk_termo INTEGER NOT NULL, 
	fk_turma INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (fk_termo, fk_turma), 
	FOREIGN KEY(fk_termo) REFERENCES termos (id_termo) ON DELETE CASCADE, 
	FOREIGN KEY(fk_turma) REFERENCES turmas (id_turma) ON DELETE CASCADE
)

;


CREATE TABLE IF NOT EXISTS termo_radicais (
	id SERIAL NOT NULL, 
	fk_termo INTEGER NOT NULL, 
	fk_radical INTEGER NOT NULL, 
	ordem INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (fk_termo, ordem), 
	FOREIGN KEY(fk_termo) REFERENCES termos (id_termo) ON DELETE CASCADE, 
	FOREIGN KEY(fk_radical) REFERENCES radicais (id_radical) ON DELETE CASCADE
)

;


CREATE TABLE IF NOT EXISTS trilha_termos (
	id SERIAL NOT NULL, 
	fk_trilha INTEGER NOT NULL, 
	fk_termo INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (fk_trilha, fk_termo), 
	FOREIGN KEY(fk_trilha) REFERENCES trilhas (id_trilha) ON DELETE CASCADE, 
	FOREIGN KEY(fk_termo) REFERENCES termos (id_termo) ON DELETE CASCADE
)

;


CREATE TABLE IF NOT EXISTS turma_trilha (
	id SERIAL NOT NULL, 
	fk_turma INTEGER NOT NULL, 
	fk_trilha INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (fk_turma, fk_trilha), 
	FOREIGN KEY(fk_turma) REFERENCES turmas (id_turma) ON DELETE CASCADE, 
	FOREIGN KEY(fk_trilha) REFERENCES trilhas (id_trilha) ON DELETE CASCADE
)

;


CREATE TABLE IF NOT EXISTS usuario_turma (
	id SERIAL NOT NULL, 
	fk_usuario UUID NOT NULL, 
	fk_turma INTEGER NOT NULL, 
	pontuacao INTEGER, 
	data_ingresso TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	UNIQUE (fk_usuario, fk_turma), 
	FOREIGN KEY(fk_usuario) REFERENCES usuarios (id_usuario) ON DELETE CASCADE, 
	FOREIGN KEY(fk_turma) REFERENCES turmas (id_turma) ON DELETE CASCADE
)

;


CREATE TABLE IF NOT EXISTS lise_partidas (
	id VARCHAR(36) NOT NULL, 
	fk_usuario UUID NOT NULL, 
	fk_termo INTEGER NOT NULL, 
	fk_turma_trilha INTEGER, 
	jogo VARCHAR(20) NOT NULL, 
	resposta_esperada JSON NOT NULL, 
	respondida BOOLEAN NOT NULL, 
	correto BOOLEAN, 
	xp INTEGER NOT NULL, 
	novo_flashcard BOOLEAN NOT NULL, 
	criada_em TIMESTAMP WITH TIME ZONE NOT NULL, 
	respondida_em TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(fk_usuario) REFERENCES usuarios (id_usuario) ON DELETE CASCADE, 
	FOREIGN KEY(fk_termo) REFERENCES termos (id_termo) ON DELETE CASCADE, 
	FOREIGN KEY(fk_turma_trilha) REFERENCES turma_trilha (id) ON DELETE SET NULL
)

;


CREATE TABLE IF NOT EXISTS usuario_trilha_termo (
	id SERIAL NOT NULL, 
	fk_usuario UUID NOT NULL, 
	fk_turma_trilha INTEGER NOT NULL, 
	fk_termo INTEGER NOT NULL, 
	acertou BOOLEAN, 
	data_conclusao TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	UNIQUE (fk_usuario, fk_turma_trilha, fk_termo), 
	FOREIGN KEY(fk_usuario) REFERENCES usuarios (id_usuario) ON DELETE CASCADE, 
	FOREIGN KEY(fk_turma_trilha) REFERENCES turma_trilha (id) ON DELETE CASCADE, 
	FOREIGN KEY(fk_termo) REFERENCES termos (id_termo) ON DELETE CASCADE
)

;


ALTER TABLE public.trilhas ADD COLUMN IF NOT EXISTS descricao TEXT NOT NULL DEFAULT '';
ALTER TABLE public.trilhas ADD COLUMN IF NOT EXISTS area VARCHAR(100) NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS ix_lise_sessoes_fk_usuario ON lise_sessoes (fk_usuario);
CREATE INDEX IF NOT EXISTS ix_lise_sessoes_expira_em ON lise_sessoes (expira_em);
CREATE INDEX IF NOT EXISTS ix_lise_termo_turmas_fk_turma ON lise_termo_turmas (fk_turma);
CREATE INDEX IF NOT EXISTS ix_lise_termo_turmas_fk_termo ON lise_termo_turmas (fk_termo);
CREATE INDEX IF NOT EXISTS ix_lise_partidas_fk_turma_trilha ON lise_partidas (fk_turma_trilha);
CREATE INDEX IF NOT EXISTS ix_lise_partidas_fk_usuario ON lise_partidas (fk_usuario);
CREATE INDEX IF NOT EXISTS ix_lise_partidas_respondida_em ON lise_partidas (respondida_em);
CREATE INDEX IF NOT EXISTS idx_lise_radicais_fk_area ON public.radicais (fk_area);
CREATE INDEX IF NOT EXISTS idx_lise_termos_fk_area ON public.termos (fk_area);
CREATE INDEX IF NOT EXISTS idx_lise_termos_criado_por ON public.termos (criado_por);
CREATE INDEX IF NOT EXISTS idx_lise_termo_radicais_fk_radical ON public.termo_radicais (fk_radical);
CREATE INDEX IF NOT EXISTS idx_lise_turmas_fk_professor ON public.turmas (fk_professor);
CREATE INDEX IF NOT EXISTS idx_lise_usuario_turma_fk_turma ON public.usuario_turma (fk_turma);
CREATE INDEX IF NOT EXISTS idx_lise_trilhas_fk_professor ON public.trilhas (fk_professor);
CREATE INDEX IF NOT EXISTS idx_lise_trilha_termos_fk_termo ON public.trilha_termos (fk_termo);
CREATE INDEX IF NOT EXISTS idx_lise_turma_trilha_fk_trilha ON public.turma_trilha (fk_trilha);
CREATE INDEX IF NOT EXISTS idx_lise_usuario_trilha_termo_fk_turma_trilha ON public.usuario_trilha_termo (fk_turma_trilha);
CREATE INDEX IF NOT EXISTS idx_lise_usuario_trilha_termo_fk_termo ON public.usuario_trilha_termo (fk_termo);
CREATE INDEX IF NOT EXISTS idx_lise_flashcards_fk_termo ON public.flashcards (fk_termo);
CREATE INDEX IF NOT EXISTS idx_lise_lise_partidas_fk_termo ON public.lise_partidas (fk_termo);
CREATE INDEX IF NOT EXISTS idx_lise_lise_recompensas_fk_termo ON public.lise_recompensas (fk_termo);
CREATE INDEX IF NOT EXISTS idx_lise_flashcards_revisao ON public.flashcards (fk_usuario, proxima_revisao_em) WHERE ativo = true;
CREATE INDEX IF NOT EXISTS idx_lise_partidas_historico ON public.lise_partidas (fk_usuario, respondida_em) WHERE respondida = true;

-- O navegador usa somente as páginas Flask. O servidor acessa PostgreSQL via
-- DATABASE_URL (papel postgres do Supabase), sem credenciais no HTML/JavaScript.
-- RLS bloqueia acessos sem políticas; REVOKE cobre políticas legadas permissivas.

ALTER TABLE public.usuarios ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.usuarios FROM PUBLIC, anon, authenticated;
ALTER TABLE public.areas ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.areas FROM PUBLIC, anon, authenticated;
ALTER TABLE public.radicais ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.radicais FROM PUBLIC, anon, authenticated;
ALTER TABLE public.termos ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.termos FROM PUBLIC, anon, authenticated;
ALTER TABLE public.termo_radicais ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.termo_radicais FROM PUBLIC, anon, authenticated;
ALTER TABLE public.turmas ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.turmas FROM PUBLIC, anon, authenticated;
ALTER TABLE public.usuario_turma ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.usuario_turma FROM PUBLIC, anon, authenticated;
ALTER TABLE public.trilhas ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.trilhas FROM PUBLIC, anon, authenticated;
ALTER TABLE public.trilha_termos ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.trilha_termos FROM PUBLIC, anon, authenticated;
ALTER TABLE public.turma_trilha ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.turma_trilha FROM PUBLIC, anon, authenticated;
ALTER TABLE public.usuario_trilha_termo ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.usuario_trilha_termo FROM PUBLIC, anon, authenticated;
ALTER TABLE public.flashcards ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.flashcards FROM PUBLIC, anon, authenticated;
ALTER TABLE public.lise_termo_turmas ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.lise_termo_turmas FROM PUBLIC, anon, authenticated;
ALTER TABLE public.lise_sessoes ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.lise_sessoes FROM PUBLIC, anon, authenticated;
ALTER TABLE public.lise_partidas ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.lise_partidas FROM PUBLIC, anon, authenticated;
ALTER TABLE public.lise_recompensas ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.lise_recompensas FROM PUBLIC, anon, authenticated;
ALTER TABLE public.lise_conquistas ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.lise_conquistas FROM PUBLIC, anon, authenticated;
ALTER TABLE public.lise_limites_auth ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.lise_limites_auth FROM PUBLIC, anon, authenticated;

-- Registro inicial: Aluno/Professor são perfis de autocadastro neste projeto.
-- Depois do cadastro, permissões consultam public.usuarios, nunca claims editáveis.
CREATE SCHEMA IF NOT EXISTS lise_private;
REVOKE ALL ON SCHEMA lise_private FROM PUBLIC, anon, authenticated;
CREATE OR REPLACE FUNCTION lise_private.handle_new_lise_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    INSERT INTO public.usuarios (id_usuario, nome, email, perfil, criado_em)
    VALUES (
        NEW.id,
        LEFT(COALESCE(NULLIF(btrim(NEW.raw_user_meta_data->>'nome'), ''), 'Usuário'), 150),
        NEW.email,
        CASE WHEN NEW.raw_user_meta_data->>'perfil' = 'Professor' THEN 'Professor' ELSE 'Aluno' END,
        NOW()
    ) ON CONFLICT (id_usuario) DO NOTHING;
    RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION lise_private.handle_new_lise_user() FROM PUBLIC, anon, authenticated;
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
AFTER INSERT ON auth.users
FOR EACH ROW EXECUTE FUNCTION lise_private.handle_new_lise_user();

-- Fechar funções legadas expostas; esta versão não as utiliza.
DO $$
BEGIN
    IF to_regprocedure('public.incrementar_pontuacao(uuid,integer)') IS NOT NULL THEN
        REVOKE ALL ON FUNCTION public.incrementar_pontuacao(uuid,integer) FROM PUBLIC, anon, authenticated;
    END IF;
    IF to_regprocedure('public.handle_new_user()') IS NOT NULL THEN
        REVOKE ALL ON FUNCTION public.handle_new_user() FROM PUBLIC, anon, authenticated;
    END IF;
END;
$$;
COMMIT;
