"""Regras de acesso, adaptação dos dados aos templates e progresso."""
from datetime import timedelta, timezone
from zoneinfo import ZoneInfo
import unicodedata
from sqlalchemy import select, or_, func
from flask import abort
from .models import *

TZ = ZoneInfo('America/Sao_Paulo')
def aware(dt):
    return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt


def normalize(value):
    value = unicodedata.normalize('NFD', value.casefold().strip())
    return ''.join(c for c in value if not unicodedata.combining(c) and c.isalnum())


def visible_terms(uid):
    shared = select(TermoTurma.fk_termo).join(Matricula, Matricula.fk_turma == TermoTurma.fk_turma).where(Matricula.fk_usuario == uid)
    return select(Termo).where(or_(Termo.criado_pelo_professor.is_(False), Termo.criado_pelo_professor.is_(None), Termo.criado_por == uid, Termo.id_termo.in_(shared)))


def visible_term(db, uid, term_id):
    term = db.scalar(visible_terms(uid).where(Termo.id_termo == term_id))
    if not term:
        abort(404)
    return term


def owned_class(db, uid, turma_id):
    row = db.scalar(select(Turma).where(Turma.id_turma == turma_id, Turma.fk_professor == uid))
    if not row:
        abort(404)
    return row


def owned_trail(db, uid, trail_id):
    row = db.scalar(select(Trilha).where(Trilha.id_trilha == trail_id, Trilha.fk_professor == uid))
    if not row:
        abort(404)
    return row


def assignment(db, user, ident):
    row = db.get(TurmaTrilha, ident)
    if not row:
        abort(404)
    turma = db.get(Turma, row.fk_turma)
    enrolled = db.scalar(select(Matricula.id).where(Matricula.fk_turma == row.fk_turma, Matricula.fk_usuario == user.id_usuario))
    if turma.fk_professor != user.id_usuario and not enrolled:
        abort(404)
    return row


def term_views(db, terms):
    if not terms:
        return []
    areas = {x.id_area: x.nome for x in db.scalars(select(Area))}
    pairs = db.execute(select(TermoRadical, Radical).join(Radical).where(TermoRadical.fk_termo.in_([x.id_termo for x in terms])).order_by(TermoRadical.ordem)).all()
    radicals = {}
    for link, rad in pairs:
        radicals.setdefault(link.fk_termo, []).append(dict(id=link.id, radical_id=rad.id_radical, text=rad.nome, meaning=rad.significado, type=rad.classificacao))
    return [dict(id=t.id_termo, name=t.palavra_completa, definition=t.definicao_biologica, area=areas.get(t.fk_area, 'Geral'), difficulty=max(1, min(3, len(radicals.get(t.id_termo, [])))), radical_list=radicals.get(t.id_termo, []), private=bool(t.criado_pelo_professor)) for t in terms]


def trail_views(db, trails):
    links = db.scalars(select(TrilhaTermo).where(TrilhaTermo.fk_trilha.in_([t.id_trilha for t in trails]))).all() if trails else []
    return [dict(id=t.id_trilha, name=t.nome, description=t.descricao, area=t.area or 'Todas as áreas', terms=[r.fk_termo for r in links if r.fk_trilha == t.id_trilha]) for t in trails]


def class_views(db, classes):
    ids = [c.id_turma for c in classes]
    students = db.scalars(select(Matricula).where(Matricula.fk_turma.in_(ids))).all() if ids else []
    trails = db.scalars(select(TurmaTrilha).where(TurmaTrilha.fk_turma.in_(ids))).all() if ids else []
    return [dict(id=c.id_turma, name=c.nome, code=c.codigo, created_at=aware(c.criado_em).astimezone(TZ).strftime('%d/%m/%Y') if c.criado_em else '', alunos=[m.fk_usuario for m in students if m.fk_turma == c.id_turma], trilhas=[t.fk_trilha for t in trails if t.fk_turma == c.id_turma]) for c in classes]


def streak(rows):
    days = {aware(p.respondida_em).astimezone(TZ).date() for p in rows if p.respondida_em}
    today = utcnow().astimezone(TZ).date()
    current = today if today in days else today - timedelta(days=1)
    count = 0
    while current in days:
        count += 1
        current -= timedelta(days=1)
    return count


def stats(rows):
    xp = sum(p.xp for p in rows)
    level = 1 + xp // 100
    return dict(xp=xp, nivel=level, jogadas=len(rows), streak=streak(rows), last_activity=max((aware(p.respondida_em) for p in rows if p.respondida_em), default=None))


def progress_percent(db, uid, link):
    return progress_detail(db, uid, link)['percent']


def progress_detail(db, uid, link):
    term_ids = set(db.scalars(select(TrilhaTermo.fk_termo).where(TrilhaTermo.fk_trilha == link.fk_trilha)))
    done = set(db.scalars(select(Progresso.fk_termo).where(
        Progresso.fk_usuario == uid,
        Progresso.fk_turma_trilha == link.id,
        Progresso.jogado.is_(True),
    )))
    played = term_ids & done
    total = len(term_ids)
    return dict(total=total, played=len(played), percent=round(100 * len(played) / total) if total else 0,
                missing=sorted(term_ids - played))


def save_result(db, user, game, correct):
    """Executar após bloquear usuário e partida; uma transação para todos os efeitos."""
    now = utcnow()
    uid = user.id_usuario
    game.respondida = True
    game.respondida_em = now
    game.correto = correct
    if correct:
        day = now.astimezone(TZ).date()
        existing = db.scalar(select(Recompensa.id).where(Recompensa.fk_usuario == uid, Recompensa.fk_termo == game.fk_termo, Recompensa.jogo == game.jogo, Recompensa.dia == day))
        if not existing:
            db.add(Recompensa(fk_usuario=uid, fk_termo=game.fk_termo, jogo=game.jogo, dia=day))
            game.xp = {
                'decifrador': 15, 'flashcard': 5,
                'familia_palavras': 10, 'memoria': 10,
            }[game.jogo]
        if game.jogo != 'flashcard':
            card = db.scalar(select(Flashcard).where(Flashcard.fk_usuario == uid, Flashcard.fk_termo == game.fk_termo))
            if not card:
                db.add(Flashcard(fk_usuario=uid, fk_termo=game.fk_termo))
                game.novo_flashcard = True
            elif not card.ativo:
                card.ativo = True
                card.proxima_revisao_em = now
                game.novo_flashcard = True
    if game.fk_turma_trilha:
        link = db.get(TurmaTrilha, game.fk_turma_trilha)
        row = db.scalar(select(Progresso).where(Progresso.fk_usuario == uid, Progresso.fk_turma_trilha == link.id, Progresso.fk_termo == game.fk_termo))
        if row:
            if not row.jogado:
                row.data_conclusao = now
            row.jogado = True
            row.acertou = bool(row.acertou or correct)
        else:
            db.add(Progresso(fk_usuario=uid, fk_turma_trilha=link.id, fk_termo=game.fk_termo,
                             acertou=correct, jogado=True))
    if correct:
        if game.fk_turma_trilha:
            link = db.get(TurmaTrilha, game.fk_turma_trilha)
            enrollment = db.scalar(select(Matricula).where(Matricula.fk_usuario == uid, Matricula.fk_turma == link.fk_turma))
            if enrollment:
                enrollment.pontuacao = (enrollment.pontuacao or 0) + game.xp
    db.flush()
