"""Mapeamento das tabelas originais e extensões da versão Flask integrada."""
from datetime import datetime, timezone
from sqlalchemy import (Boolean, Column, Date, DateTime, ForeignKey, Index, Integer, JSON,
                        String, Text, UniqueConstraint, Uuid)
from sqlalchemy.orm import DeclarativeBase


def utcnow():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Usuario(Base):
    __tablename__ = 'usuarios'
    id_usuario = Column(Uuid(as_uuid=False), primary_key=True)
    nome = Column(String(150), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    perfil = Column(String(20), nullable=False)
    criado_em = Column(DateTime(timezone=True), default=utcnow)
    ultimo_acesso_em = Column(DateTime(timezone=True))


class Area(Base):
    __tablename__ = 'areas'
    id_area = Column(Integer, primary_key=True)
    nome = Column(String(100), unique=True, nullable=False)


class Radical(Base):
    __tablename__ = 'radicais'
    id_radical = Column(Integer, primary_key=True)
    nome = Column(String(100), nullable=False)
    significado = Column(Text, nullable=False)
    classificacao = Column(String(20), nullable=False)
    fk_area = Column(Integer, ForeignKey('areas.id_area'))


class Termo(Base):
    __tablename__ = 'termos'
    id_termo = Column(Integer, primary_key=True)
    palavra_completa = Column(String(200), nullable=False)
    definicao_biologica = Column(Text, nullable=False)
    fk_area = Column(Integer, ForeignKey('areas.id_area'))
    criado_por = Column(Uuid(as_uuid=False), ForeignKey('usuarios.id_usuario'))
    criado_pelo_professor = Column(Boolean, default=False)
    criado_em = Column(DateTime(timezone=True), default=utcnow)


class TermoRadical(Base):
    __tablename__ = 'termo_radicais'
    id = Column(Integer, primary_key=True)
    fk_termo = Column(Integer, ForeignKey('termos.id_termo', ondelete='CASCADE'), nullable=False)
    fk_radical = Column(Integer, ForeignKey('radicais.id_radical', ondelete='CASCADE'), nullable=False)
    ordem = Column(Integer, nullable=False)
    __table_args__ = (UniqueConstraint('fk_termo', 'ordem'),)


class Turma(Base):
    __tablename__ = 'turmas'
    id_turma = Column(Integer, primary_key=True)
    nome = Column(String(150), nullable=False)
    codigo = Column(String(6), unique=True, nullable=False)
    fk_professor = Column(Uuid(as_uuid=False), ForeignKey('usuarios.id_usuario'), nullable=False)
    criado_em = Column(DateTime(timezone=True), default=utcnow)


class Matricula(Base):
    __tablename__ = 'usuario_turma'
    id = Column(Integer, primary_key=True)
    fk_usuario = Column(Uuid(as_uuid=False), ForeignKey('usuarios.id_usuario', ondelete='CASCADE'), nullable=False)
    fk_turma = Column(Integer, ForeignKey('turmas.id_turma', ondelete='CASCADE'), nullable=False)
    pontuacao = Column(Integer, default=0)
    data_ingresso = Column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint('fk_usuario', 'fk_turma'),)


class Trilha(Base):
    __tablename__ = 'trilhas'
    id_trilha = Column(Integer, primary_key=True)
    nome = Column(String(150), nullable=False)
    fk_professor = Column(Uuid(as_uuid=False), ForeignKey('usuarios.id_usuario'), nullable=False)
    criado_em = Column(DateTime(timezone=True), default=utcnow)
    # Colunas adicionadas pela migração desta versão.
    descricao = Column(Text, nullable=False, default='')
    area = Column(String(100), nullable=False, default='')


class TrilhaTermo(Base):
    __tablename__ = 'trilha_termos'
    id = Column(Integer, primary_key=True)
    fk_trilha = Column(Integer, ForeignKey('trilhas.id_trilha', ondelete='CASCADE'), nullable=False)
    fk_termo = Column(Integer, ForeignKey('termos.id_termo', ondelete='CASCADE'), nullable=False)
    __table_args__ = (UniqueConstraint('fk_trilha', 'fk_termo'),)


class TurmaTrilha(Base):
    __tablename__ = 'turma_trilha'
    id = Column(Integer, primary_key=True)
    fk_turma = Column(Integer, ForeignKey('turmas.id_turma', ondelete='CASCADE'), nullable=False)
    fk_trilha = Column(Integer, ForeignKey('trilhas.id_trilha', ondelete='CASCADE'), nullable=False)
    data_limite = Column(Date)
    __table_args__ = (UniqueConstraint('fk_turma', 'fk_trilha'),)


class Progresso(Base):
    __tablename__ = 'usuario_trilha_termo'
    id = Column(Integer, primary_key=True)
    fk_usuario = Column(Uuid(as_uuid=False), ForeignKey('usuarios.id_usuario', ondelete='CASCADE'), nullable=False)
    fk_turma_trilha = Column(Integer, ForeignKey('turma_trilha.id', ondelete='CASCADE'), nullable=False)
    fk_termo = Column(Integer, ForeignKey('termos.id_termo', ondelete='CASCADE'), nullable=False)
    acertou = Column(Boolean, default=False)
    jogado = Column(Boolean, default=False, nullable=False)
    data_conclusao = Column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint('fk_usuario', 'fk_turma_trilha', 'fk_termo'),)


class Flashcard(Base):
    __tablename__ = 'flashcards'
    id_flashcard = Column(Integer, primary_key=True)
    fk_usuario = Column(Uuid(as_uuid=False), ForeignKey('usuarios.id_usuario', ondelete='CASCADE'), nullable=False)
    fk_termo = Column(Integer, ForeignKey('termos.id_termo', ondelete='CASCADE'), nullable=False)
    ativo = Column(Boolean, default=True)
    dificuldade = Column(String(20), default='fácil')
    proxima_revisao_em = Column(DateTime(timezone=True), default=utcnow)
    criado_em = Column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint('fk_usuario', 'fk_termo'),)


class TermoTurma(Base):
    __tablename__ = 'lise_termo_turmas'
    id = Column(Integer, primary_key=True)
    fk_termo = Column(Integer, ForeignKey('termos.id_termo', ondelete='CASCADE'), nullable=False, index=True)
    fk_turma = Column(Integer, ForeignKey('turmas.id_turma', ondelete='CASCADE'), nullable=False, index=True)
    __table_args__ = (UniqueConstraint('fk_termo', 'fk_turma'),)


class Sessao(Base):
    __tablename__ = 'lise_sessoes'
    id = Column(String(64), primary_key=True)  # SHA-256 do identificador aleatório.
    fk_usuario = Column(Uuid(as_uuid=False), ForeignKey('usuarios.id_usuario', ondelete='CASCADE'), nullable=False, index=True)
    expira_em = Column(DateTime(timezone=True), nullable=False, index=True)


class Partida(Base):
    __tablename__ = 'lise_partidas'
    id = Column(String(36), primary_key=True)
    fk_usuario = Column(Uuid(as_uuid=False), ForeignKey('usuarios.id_usuario', ondelete='CASCADE'), nullable=False, index=True)
    fk_termo = Column(Integer, ForeignKey('termos.id_termo', ondelete='CASCADE'), nullable=False)
    fk_turma_trilha = Column(Integer, ForeignKey('turma_trilha.id', ondelete='SET NULL'), index=True)
    jogo = Column(String(20), nullable=False)
    resposta_esperada = Column(JSON, nullable=False)
    respondida = Column(Boolean, default=False, nullable=False)
    correto = Column(Boolean)
    xp = Column(Integer, default=0, nullable=False)
    novo_flashcard = Column(Boolean, default=False, nullable=False)
    criada_em = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    respondida_em = Column(DateTime(timezone=True), index=True)


class Recompensa(Base):
    __tablename__ = 'lise_recompensas'
    id = Column(Integer, primary_key=True)
    fk_usuario = Column(Uuid(as_uuid=False), ForeignKey('usuarios.id_usuario', ondelete='CASCADE'), nullable=False)
    fk_termo = Column(Integer, ForeignKey('termos.id_termo', ondelete='CASCADE'), nullable=False)
    jogo = Column(String(20), nullable=False)
    dia = Column(Date, nullable=False)
    __table_args__ = (UniqueConstraint('fk_usuario', 'fk_termo', 'jogo', 'dia'),)


class Conquista(Base):
    __tablename__ = 'lise_conquistas'
    id = Column(Integer, primary_key=True)
    fk_usuario = Column(Uuid(as_uuid=False), ForeignKey('usuarios.id_usuario', ondelete='CASCADE'), nullable=False)
    codigo = Column(String(30), nullable=False)
    criada_em = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    __table_args__ = (UniqueConstraint('fk_usuario', 'codigo'),)


class LimiteAuth(Base):
    __tablename__ = 'lise_limites_auth'
    chave = Column(String(64), primary_key=True)
    tentativas = Column(Integer, nullable=False, default=0)
    inicio = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class Colecao(Base):
    __tablename__ = 'lise_colecoes'
    id = Column(Integer, primary_key=True)
    fk_usuario = Column(Uuid(as_uuid=False), ForeignKey('usuarios.id_usuario', ondelete='CASCADE'), nullable=False, index=True)
    nome = Column(String(100), nullable=False)
    criada_em = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class ColecaoTermo(Base):
    __tablename__ = 'lise_colecao_termos'
    id = Column(Integer, primary_key=True)
    fk_colecao = Column(Integer, ForeignKey('lise_colecoes.id', ondelete='CASCADE'), nullable=False, index=True)
    fk_termo = Column(Integer, ForeignKey('termos.id_termo', ondelete='CASCADE'), nullable=False, index=True)
    __table_args__ = (UniqueConstraint('fk_colecao', 'fk_termo'),)


class FavoritoTermo(Base):
    __tablename__ = 'lise_favoritos_termos'
    id = Column(Integer, primary_key=True)
    fk_usuario = Column(Uuid(as_uuid=False), ForeignKey('usuarios.id_usuario', ondelete='CASCADE'), nullable=False, index=True)
    fk_termo = Column(Integer, ForeignKey('termos.id_termo', ondelete='CASCADE'), nullable=False, index=True)
    __table_args__ = (UniqueConstraint('fk_usuario', 'fk_termo'),)


class FavoritoRadical(Base):
    __tablename__ = 'lise_favoritos_radicais'
    id = Column(Integer, primary_key=True)
    fk_usuario = Column(Uuid(as_uuid=False), ForeignKey('usuarios.id_usuario', ondelete='CASCADE'), nullable=False, index=True)
    fk_radical = Column(Integer, ForeignKey('radicais.id_radical', ondelete='CASCADE'), nullable=False, index=True)
    __table_args__ = (UniqueConstraint('fk_usuario', 'fk_radical'),)


class GameSession(Base):
    __tablename__ = 'lise_game_sessions'
    id = Column(String(36), primary_key=True)
    fk_usuario = Column(Uuid(as_uuid=False), ForeignKey('usuarios.id_usuario', ondelete='CASCADE'), nullable=False, index=True)
    fk_turma = Column(Integer, ForeignKey('turmas.id_turma', ondelete='CASCADE'), index=True)
    fk_turma_trilha = Column(Integer, ForeignKey('turma_trilha.id', ondelete='SET NULL'), index=True)
    jogo = Column(String(24), nullable=False)
    source_type = Column(String(24), nullable=False)
    source_id = Column(Integer)
    total = Column(Integer, nullable=False, default=0)
    corretas = Column(Integer, nullable=False, default=0)
    xp = Column(Integer, nullable=False, default=0)
    pontuacao = Column(Integer, nullable=False, default=0)
    criada_em = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    finalizada_em = Column(DateTime(timezone=True))
    __table_args__ = (Index('ix_lise_game_sessions_class_date', 'fk_turma', 'finalizada_em'),)


class GameQuestion(Base):
    __tablename__ = 'lise_game_session_questions'
    id = Column(Integer, primary_key=True)
    fk_sessao = Column(String(36), ForeignKey('lise_game_sessions.id', ondelete='CASCADE'), nullable=False, index=True)
    fk_partida = Column(String(36), ForeignKey('lise_partidas.id', ondelete='CASCADE'), nullable=False, unique=True)
    posicao = Column(Integer, nullable=False)
    payload = Column(JSON, nullable=False)
    __table_args__ = (UniqueConstraint('fk_sessao', 'posicao'),)


class Avaliacao(Base):
    __tablename__ = 'lise_avaliacoes'
    id = Column(Integer, primary_key=True)
    fk_turma_trilha = Column(Integer, ForeignKey('turma_trilha.id', ondelete='CASCADE'), nullable=False, unique=True)
    titulo = Column(String(150), nullable=False)
    quantidade = Column(Integer, nullable=False, default=10)
    conteudo = Column(String(16), nullable=False, default='ambos')
    formato = Column(String(32), nullable=False, default='misto')
    nota_minima = Column(Integer, nullable=False, default=70)
    fk_professor = Column(Uuid(as_uuid=False), ForeignKey('usuarios.id_usuario', ondelete='CASCADE'), nullable=False)
    criada_em = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class AvaliacaoSessao(Base):
    __tablename__ = 'lise_avaliacao_sessoes'
    id = Column(String(36), primary_key=True)
    fk_avaliacao = Column(Integer, ForeignKey('lise_avaliacoes.id', ondelete='CASCADE'), nullable=False, index=True)
    fk_usuario = Column(Uuid(as_uuid=False), ForeignKey('usuarios.id_usuario', ondelete='CASCADE'), nullable=False, index=True)
    total = Column(Integer, nullable=False, default=0)
    corretas = Column(Integer, nullable=False, default=0)
    pontuacao = Column(Integer, nullable=False, default=0)
    nota_minima = Column(Integer, nullable=False, default=70)
    aprovada = Column(Boolean, nullable=False, default=False)
    criada_em = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    finalizada_em = Column(DateTime(timezone=True))
    __table_args__ = (Index('ix_lise_assessment_user_date', 'fk_usuario', 'finalizada_em'),)


class AvaliacaoQuestao(Base):
    __tablename__ = 'lise_avaliacao_questoes'
    id = Column(String(36), primary_key=True)
    fk_sessao = Column(String(36), ForeignKey('lise_avaliacao_sessoes.id', ondelete='CASCADE'), nullable=False, index=True)
    posicao = Column(Integer, nullable=False)
    fk_termo = Column(Integer, ForeignKey('termos.id_termo', ondelete='SET NULL'))
    fk_radical = Column(Integer, ForeignKey('radicais.id_radical', ondelete='SET NULL'))
    prompt = Column(Text, nullable=False)
    opcoes = Column(JSON, nullable=False)
    resposta_esperada = Column(String(80), nullable=False)
    respondida = Column(Boolean, nullable=False, default=False)
    correta = Column(Boolean)
    __table_args__ = (UniqueConstraint('fk_sessao', 'posicao'),)
