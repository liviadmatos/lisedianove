"""API JSON independente para o frontend estático da LISE.

Os endpoints antigos continuam disponíveis para migração gradual, mas o novo
frontend usa somente /api/v1 e autenticação Bearer sem cookies entre origens.
"""
from datetime import datetime, time, timedelta, timezone
from functools import wraps
import hashlib
import random
import re
import secrets
import uuid

from flask import Blueprint, abort, current_app, g, jsonify, request
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import HTTPException
from supabase_auth.errors import AuthApiError

from .models import *
from .services import (
    TZ, assignment, aware, class_views, normalize, owned_class, owned_trail,
    progress_detail, progress_percent, save_result, stats, term_views, trail_views,
    utcnow, visible_term, visible_terms,
)

api = Blueprint('lise_api_v1', __name__, url_prefix='/api/v1')


def _body():
    value = request.get_json(silent=True)
    return value if isinstance(value, dict) else {}


def _fail(code, message):
    abort(code, description=message)


def _require_user(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not getattr(g, 'user', None):
            _fail(401, 'Entre novamente para continuar.')
        last = aware(g.user.ultimo_acesso_em)
        now = utcnow()
        if not last or last < now - timedelta(minutes=5):
            g.user.ultimo_acesso_em = now
            g.db.commit()
        return fn(*args, **kwargs)
    return wrapped


def _teacher(fn):
    @_require_user
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if g.user.perfil != 'Professor':
            _fail(403, 'Esta função é exclusiva do professor.')
        return fn(*args, **kwargs)
    return wrapped


def _student(fn):
    @_require_user
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if g.user.perfil != 'Aluno':
            _fail(403, 'Esta função é exclusiva do aluno.')
        return fn(*args, **kwargs)
    return wrapped


def _json_error(message, status):
    return jsonify(error=message), status


@api.errorhandler(HTTPException)
def _http_error(error):
    return _json_error(error.description or 'Não foi possível concluir a solicitação.', error.code or 400)


@api.errorhandler(Exception)
def _unexpected_error(error):
    if current_app.testing:
        raise error
    current_app.logger.error('Falha na API LISE: %s', type(error).__name__)
    return _json_error('Ocorreu um erro. Tente novamente em instantes.', 503)


def _auth_client():
    return current_app.extensions['lise_auth_client']()


def _auth_limit():
    secret = current_app.config['SECRET_KEY']
    key = hashlib.sha256(f'{secret}:{request.remote_addr}:{request.endpoint}'.encode()).hexdigest()
    now = utcnow()
    row = g.db.scalar(select(LimiteAuth).where(LimiteAuth.chave == key).with_for_update())
    if not row:
        try:
            with g.db.begin_nested():
                row = LimiteAuth(chave=key, tentativas=0, inicio=now)
                g.db.add(row)
                g.db.flush()
        except IntegrityError:
            row = g.db.scalar(select(LimiteAuth).where(LimiteAuth.chave == key).with_for_update())
    if aware(row.inicio) < now - timedelta(minutes=15):
        row.inicio, row.tentativas = now, 0
    if row.tentativas >= 15:
        _fail(429, 'Muitas tentativas. Aguarde 15 minutos e tente novamente.')
    row.tentativas += 1
    g.db.commit()


def _field(value, name, maximum, required=True):
    value = value.strip() if isinstance(value, str) else ''
    if (required and not value) or len(value) > maximum:
        _fail(400, f'Confira o campo {name}.')
    return value


def _positive_int(value, name='identificador'):
    try:
        result = int(value)
        if result < 1:
            raise ValueError
        return result
    except (TypeError, ValueError):
        _fail(400, f'{name.capitalize()} inválido.')


def _user_json(user):
    return dict(id=str(user.id_usuario), name=user.nome, email=user.email, role=user.perfil,
                last_access=aware(user.ultimo_acesso_em).isoformat() if user.ultimo_acesso_em else None)


def _token_session(user, remember=False):
    token = secrets.token_urlsafe(40)
    expires = utcnow() + (timedelta(days=30) if remember else timedelta(hours=12))
    g.db.add(Sessao(id=hashlib.sha256(token.encode()).hexdigest(), fk_usuario=user.id_usuario, expira_em=expires))
    user.ultimo_acesso_em = utcnow()
    g.db.commit()
    return token, expires


@api.get('/healthz')
def healthz():
    g.db.execute(select(1))
    return jsonify(status='ok', service='lise-api')


@api.post('/auth/login')
def auth_login():
    _auth_limit()
    data = _body()
    email = _field(data.get('email', ''), 'e-mail', 255).lower()
    password = data.get('password', '')
    if not isinstance(password, str) or not 1 <= len(password) <= 128:
        _fail(400, 'Confira o e-mail e a senha.')
    user = None
    if current_app.config['DEMO_MODE']:
        if password == 'LiseDemo123!':
            user = g.db.scalar(select(Usuario).where(func.lower(Usuario.email) == email))
    else:
        try:
            response = _auth_client().auth.sign_in_with_password({'email': email, 'password': password})
            user = g.db.get(Usuario, str(response.user.id)) if response.user else None
        except AuthApiError:
            user = None
    if not user:
        _fail(401, 'Não foi possível entrar. Confira as credenciais e a confirmação do e-mail.')
    token, expires = _token_session(user, bool(data.get('remember')))
    return jsonify(access_token=token, token_type='Bearer', expires_at=expires.isoformat(), user=_user_json(user))


@api.post('/auth/register')
def auth_register():
    _auth_limit()
    if current_app.config['DEMO_MODE']:
        _fail(403, 'O cadastro está desativado na demonstração local.')
    data = _body()
    name = _field(data.get('name', ''), 'nome', 150)
    email = _field(data.get('email', ''), 'e-mail', 255).lower()
    password = data.get('password', '')
    role = {'ALUNO': 'Aluno', 'PROFESSOR': 'Professor'}.get(str(data.get('role', '')).upper())
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email) or not role or not isinstance(password, str) or not 8 <= len(password) <= 128:
        _fail(400, 'Confira os dados. A senha precisa ter ao menos 8 caracteres.')
    if role == 'Professor':
        invite = str(data.get('teacher_code', '')).strip()
        configured = current_app.config.get('TEACHER_INVITE_CODE', '')
        if not configured or not secrets.compare_digest(invite, configured):
            _fail(403, 'O código de acesso do professor é inválido.')
    try:
        _auth_client().auth.sign_up({'email': email, 'password': password, 'options': {
            'data': {'nome': name, 'perfil': role},
            'email_redirect_to': current_app.config['FRONTEND_URL'] + '/?confirmed=1'}})
    except AuthApiError:
        _fail(400, 'Não foi possível concluir o cadastro. Confira os dados e tente novamente.')
    return jsonify(message='Se o cadastro puder ser concluído, você receberá as instruções por e-mail.'), 201


@api.post('/auth/recovery')
def auth_recovery():
    _auth_limit()
    if current_app.config['DEMO_MODE']:
        return jsonify(message='A recuperação por e-mail está disponível na configuração com Supabase.')
    email = _field(_body().get('email', ''), 'e-mail', 255).lower()
    try:
        _auth_client().auth.reset_password_for_email(email, {
            'redirect_to': current_app.config['FRONTEND_URL'] + '/?mode=recovery'})
    except AuthApiError:
        pass
    return jsonify(message='Se houver uma conta com esse e-mail, enviaremos um link para redefinir a senha.')


@api.post('/auth/password')
def auth_password():
    data = _body()
    password = data.get('password', '')
    token_hash = data.get('token_hash', '')
    if not isinstance(password, str) or not 8 <= len(password) <= 128 or not token_hash:
        _fail(400, 'Link de recuperação inválido ou expirado.')
    try:
        client = _auth_client()
        response = client.auth.verify_otp({'token_hash': token_hash, 'type': 'recovery'})
        if not response.user or not response.session:
            _fail(400, 'Link de recuperação inválido ou expirado.')
        client.auth.update_user({'password': password})
        g.db.execute(delete(Sessao).where(Sessao.fk_usuario == str(response.user.id)))
        g.db.commit()
    except AuthApiError:
        _fail(400, 'Link de recuperação inválido ou expirado.')
    return jsonify(message='Senha atualizada. Entre novamente.')


@api.post('/auth/logout')
@_require_user
def auth_logout():
    authorization = request.headers.get('Authorization', '')
    token = authorization[7:].strip() if authorization.lower().startswith('bearer ') else ''
    if token:
        g.db.execute(delete(Sessao).where(Sessao.id == hashlib.sha256(token.encode()).hexdigest()))
        g.db.commit()
    return jsonify(message='Você saiu da sua conta.')


@api.get('/auth/me')
@_require_user
def auth_me():
    return jsonify(user=_user_json(g.user))


def _favorite_ids(uid):
    terms = set(g.db.scalars(select(FavoritoTermo.fk_termo).where(FavoritoTermo.fk_usuario == uid)))
    radicals = set(g.db.scalars(select(FavoritoRadical.fk_radical).where(FavoritoRadical.fk_usuario == uid)))
    return terms, radicals


def _term_data(terms, uid, favorite_ids=None):
    rows = term_views(g.db, terms)
    if favorite_ids is None:
        favorite_ids, _ = _favorite_ids(uid)
    own = {t.id_termo for t in terms if t.criado_por == uid}
    for item in rows:
        item['favorite'] = item['id'] in favorite_ids
        item['created_by_me'] = item['id'] in own
        item['private'] = item['id'] in own and bool(next(t for t in terms if t.id_termo == item['id']).criado_pelo_professor)
    return rows


def _radical_data(radicals, uid, favorite_ids=None):
    if favorite_ids is None:
        _, favorite_ids = _favorite_ids(uid)
    areas = {area.id_area: area.nome for area in g.db.scalars(select(Area))}
    visible_ids = visible_terms(uid).with_only_columns(Termo.id_termo)
    counts = dict(g.db.execute(select(TermoRadical.fk_radical, func.count(TermoRadical.id))
                               .where(TermoRadical.fk_termo.in_(visible_ids))
                               .group_by(TermoRadical.fk_radical)).all())
    output = []
    for radical in radicals:
        count = counts.get(radical.id_radical, 0)
        output.append(dict(id=radical.id_radical, name=radical.nome, meaning=radical.significado,
                           classification=radical.classificacao, area=areas.get(radical.fk_area, 'Geral'),
                           related_count=count, favorite=radical.id_radical in favorite_ids))
    return output


def _visible_radicals(uid):
    """Radicais ligados a termos públicos, próprios ou compartilhados com o usuário."""
    term_ids = visible_terms(uid).with_only_columns(Termo.id_termo)
    linked_radicals = select(TermoRadical.fk_radical).where(TermoRadical.fk_termo.in_(term_ids))
    return select(Radical).where(
        Radical.id_radical.in_(linked_radicals),
        func.trim(Radical.nome) != '',
        func.trim(Radical.significado) != '',
    )


def _visible_radical(uid, radical_id):
    radical = g.db.scalar(_visible_radicals(uid).where(Radical.id_radical == radical_id))
    if not radical:
        _fail(404, 'Radical não encontrado.')
    return radical


@api.get('/meta')
@_require_user
def meta():
    return jsonify(areas=[dict(id=a.id_area, name=a.nome) for a in g.db.scalars(select(Area).order_by(Area.nome))])


@api.get('/dashboard')
@_require_user
def dashboard():
    uid = g.user.id_usuario
    if g.user.perfil == 'Professor':
        classes = g.db.scalars(select(Turma).where(Turma.fk_professor == uid).order_by(Turma.criado_em.desc())).all()
        trails = g.db.scalars(select(Trilha).where(Trilha.fk_professor == uid).order_by(Trilha.criado_em.desc())).all()
        return jsonify(role='Professor', classes=class_views(g.db, classes), trails=trail_views(g.db, trails),
                       areas=[dict(id=a.id_area, name=a.nome) for a in g.db.scalars(select(Area).order_by(Area.nome))])
    classes = g.db.scalars(select(Turma).join(Matricula, Matricula.fk_turma == Turma.id_turma)
                           .where(Matricula.fk_usuario == uid).order_by(Turma.criado_em.desc())).all()
    rows = g.db.scalars(select(Partida).where(Partida.fk_usuario == uid, Partida.respondida.is_(True))).all()
    collections = g.db.scalars(select(Colecao).where(Colecao.fk_usuario == uid).order_by(Colecao.criada_em.desc())).all()
    return jsonify(role='Aluno', classes=class_views(g.db, classes), stats=stats(rows),
                   collections=[dict(id=c.id, name=c.nome) for c in collections])


@api.get('/classes')
@_require_user
def classes_list():
    if g.user.perfil == 'Professor':
        rows = g.db.scalars(select(Turma).where(Turma.fk_professor == g.user.id_usuario).order_by(Turma.criado_em.desc())).all()
    else:
        rows = g.db.scalars(select(Turma).join(Matricula, Matricula.fk_turma == Turma.id_turma)
                            .where(Matricula.fk_usuario == g.user.id_usuario).order_by(Turma.criado_em.desc())).all()
    return jsonify(classes=class_views(g.db, rows))


@api.post('/classes')
@_teacher
def class_create():
    name = _field(_body().get('name', ''), 'nome da turma', 150)
    for _ in range(5):
        try:
            with g.db.begin_nested():
                row = Turma(nome=name, codigo=''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(6)), fk_professor=g.user.id_usuario)
                g.db.add(row)
                g.db.flush()
            g.db.commit()
            return jsonify(id=row.id_turma, name=row.nome, code=row.codigo), 201
        except IntegrityError:
            continue
    _fail(503, 'Não foi possível gerar o código. Tente novamente.')


@api.post('/classes/join')
@_student
def class_join():
    code = _field(_body().get('code', ''), 'código da turma', 6).upper()
    row = g.db.scalar(select(Turma).where(Turma.codigo == code))
    if not row:
        _fail(404, 'Código de turma não encontrado.')
    existing = g.db.scalar(select(Matricula.id).where(Matricula.fk_usuario == g.user.id_usuario, Matricula.fk_turma == row.id_turma))
    if not existing:
        g.db.add(Matricula(fk_usuario=g.user.id_usuario, fk_turma=row.id_turma))
        g.db.commit()
    return jsonify(id=row.id_turma, name=row.nome, message='Você entrou na turma.')


def _class_for_user(class_id):
    row = g.db.get(Turma, _positive_int(class_id, 'turma'))
    if not row:
        _fail(404, 'Turma não encontrada.')
    if g.user.perfil == 'Professor':
        if row.fk_professor != g.user.id_usuario:
            _fail(404, 'Turma não encontrada.')
    elif not g.db.scalar(select(Matricula.id).where(Matricula.fk_turma == row.id_turma, Matricula.fk_usuario == g.user.id_usuario)):
        _fail(404, 'Turma não encontrada.')
    return row


def _local_day_bounds(day):
    start = datetime.combine(day, time.min, tzinfo=TZ).astimezone(timezone.utc)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=TZ).astimezone(timezone.utc)
    return start, end


def _parse_date(value, field_name='data'):
    if not value:
        return None
    try:
        return datetime.strptime(str(value), '%Y-%m-%d').date()
    except ValueError:
        _fail(400, f'{field_name.capitalize()} inválida.')


def _assessment_config(link):
    row = g.db.scalar(select(Avaliacao).where(Avaliacao.fk_turma_trilha == link.id))
    if not row:
        return None
    return dict(id=row.id, title=row.titulo, question_count=row.quantidade,
                content=row.conteudo, mode=row.formato, pass_score=row.nota_minima)


def _mark_practiced_terms(uid, link_id, term_ids):
    """Marca somente termos desta atribuição, sem aceitar IDs fora da trilha."""
    if not link_id:
        return
    link = g.db.get(TurmaTrilha, link_id)
    if not link:
        return
    valid = set(g.db.scalars(select(TrilhaTermo.fk_termo).where(
        TrilhaTermo.fk_trilha == link.fk_trilha,
        TrilhaTermo.fk_termo.in_(set(int(value) for value in term_ids if str(value).isdigit()))
    ))) if term_ids else set()
    if not valid:
        return
    existing = {row.fk_termo: row for row in g.db.scalars(select(Progresso).where(
        Progresso.fk_usuario == uid,
        Progresso.fk_turma_trilha == link.id,
        Progresso.fk_termo.in_(valid),
    ))}
    for ident in valid:
        row = existing.get(ident)
        if row:
            if not row.jogado:
                row.data_conclusao = utcnow()
            row.jogado = True
        else:
            g.db.add(Progresso(fk_usuario=uid, fk_turma_trilha=link.id,
                               fk_termo=ident, acertou=False, jogado=True))


def _assessment_question_pool(user_id, link, assessment):
    trail_terms = g.db.scalars(visible_terms(user_id)
                               .join(TrilhaTermo, TrilhaTermo.fk_termo == Termo.id_termo)
                               .where(TrilhaTermo.fk_trilha == link.fk_trilha)
                               .order_by(Termo.id_termo)).all()
    terms = _term_data(trail_terms, user_id)
    radical_by_id = {}
    for term in terms:
        for radical in term.get('radical_list', []):
            radical_by_id[radical['radical_id']] = radical
    radicals = list(radical_by_id.values())
    visible = g.db.scalars(visible_terms(user_id).order_by(Termo.id_termo).limit(1000)).all()
    term_options = _term_data(visible, user_id)
    all_radicals = _radical_data(g.db.scalars(_visible_radicals(user_id).order_by(Radical.id_radical).limit(1000)).all(), user_id)
    modes = (['termo_definicao', 'definicao_termo'] if assessment.conteudo == 'termos' else
             ['radical_significado', 'significado_radical'] if assessment.conteudo == 'radicais' else
             ['termo_definicao', 'definicao_termo', 'radical_significado', 'significado_radical'])
    if assessment.formato != 'misto':
        modes = [assessment.formato]
    pool = []
    rng = random.SystemRandom()

    def options_for(correct_label, distractors):
        candidates = [label for label in distractors if label and label.casefold() != correct_label.casefold()]
        rng.shuffle(candidates)
        seen = {correct_label.casefold()}
        chosen = []
        for label in candidates:
            if label.casefold() in seen:
                continue
            seen.add(label.casefold())
            chosen.append(dict(id=secrets.token_urlsafe(12), label=label))
            if len(chosen) == 3:
                break
        if len(chosen) < 2:
            return None, None
        correct_id = secrets.token_urlsafe(12)
        result = [dict(id=correct_id, label=correct_label), *chosen]
        rng.shuffle(result)
        return result, correct_id

    if any(mode in modes for mode in ('termo_definicao', 'definicao_termo')):
        for term in terms:
            if 'termo_definicao' in modes:
                opts, expected = options_for(term['definition'], [item['definition'] for item in term_options]) if term_options else (None, None)
                if opts:
                    pool.append(dict(term_id=term['id'], radical_id=None, prompt=f"Qual é a definição de {term['name']}?", options=opts, expected=expected))
            if 'definicao_termo' in modes:
                opts, expected = options_for(term['name'], [item['name'] for item in term_options]) if term_options else (None, None)
                if opts:
                    pool.append(dict(term_id=term['id'], radical_id=None, prompt=term['definition'], options=opts, expected=expected))
    if any(mode in modes for mode in ('radical_significado', 'significado_radical')):
        for radical in radicals:
            if 'radical_significado' in modes:
                opts, expected = options_for(radical['meaning'], [item['meaning'] for item in all_radicals]) if all_radicals else (None, None)
                if opts:
                    pool.append(dict(term_id=None, radical_id=radical['id'], prompt=f"O que significa o radical {radical['name']}?", options=opts, expected=expected))
            if 'significado_radical' in modes:
                opts, expected = options_for(radical['name'], [item['name'] for item in all_radicals]) if all_radicals else (None, None)
                if opts:
                    pool.append(dict(term_id=None, radical_id=radical['id'], prompt=radical['meaning'], options=opts, expected=expected))
    rng.shuffle(pool)
    return pool


def _bulk_assignment_learning_status(uid, links, include_attempts=False):
    """Carrega progresso e avaliações de várias trilhas com consultas em lote."""
    if not links:
        return {}
    link_ids = [link.id for link in links]
    trail_ids = list({link.fk_trilha for link in links})
    term_ids_by_trail = {}
    for trail_id, term_id in g.db.execute(select(TrilhaTermo.fk_trilha, TrilhaTermo.fk_termo)
                                          .where(TrilhaTermo.fk_trilha.in_(trail_ids))).all():
        term_ids_by_trail.setdefault(trail_id, set()).add(term_id)
    played_by_link, latest_play_by_link = {}, {}
    for link_id, term_id, played_at in g.db.execute(
        select(Progresso.fk_turma_trilha, Progresso.fk_termo, Progresso.data_conclusao)
        .where(Progresso.fk_usuario == uid, Progresso.fk_turma_trilha.in_(link_ids),
               Progresso.jogado.is_(True))
    ).all():
        played_by_link.setdefault(link_id, set()).add(term_id)
        if played_at:
            current = latest_play_by_link.get(link_id)
            if current is None or aware(played_at) > aware(current):
                latest_play_by_link[link_id] = played_at
    assessments = g.db.scalars(select(Avaliacao).where(Avaliacao.fk_turma_trilha.in_(link_ids))).all()
    assessment_by_link = {assessment.fk_turma_trilha: assessment for assessment in assessments}
    sessions_by_assessment = {}
    if assessments:
        for session in g.db.scalars(select(AvaliacaoSessao).where(
            AvaliacaoSessao.fk_avaliacao.in_([a.id for a in assessments]),
            AvaliacaoSessao.fk_usuario == uid,
            AvaliacaoSessao.finalizada_em.is_not(None),
        )).all():
            sessions_by_assessment.setdefault(session.fk_avaliacao, []).append(session)

    today = utcnow().astimezone(TZ).date()
    labels = {
        'concluida_no_prazo': 'Concluída no prazo',
        'concluida_com_atraso': 'Concluída com atraso',
        'concluida': 'Concluída',
        'atrasado': 'Atrasado',
        'sem_prazo': 'Sem prazo',
        'aguardando_avaliacao': 'Aguardando avaliação',
        'avaliacao_nao_configurada': 'Avaliação não configurada',
        'em_dia': 'Em dia',
    }
    result = {}
    for link in links:
        terms = term_ids_by_trail.get(link.fk_trilha, set())
        played = terms & played_by_link.get(link.id, set())
        total = len(terms)
        percent = round(100 * len(played) / total) if total else 0
        progress = dict(total=total, played=len(played), percent=percent, missing=sorted(terms - played))
        assessment = assessment_by_link.get(link.id)
        sessions = sessions_by_assessment.get(assessment.id, []) if assessment else []
        best_session = max(sessions, key=lambda session: (session.pontuacao, aware(session.finalizada_em))) if sessions else None
        passed_sessions = [session for session in sessions if session.aprovada]
        first_passed = min(passed_sessions, key=lambda session: aware(session.finalizada_em)) if passed_sessions else None
        completed = bool(total and percent == 100 and first_passed)
        due = link.data_limite
        completion_at = None
        if completed:
            latest_play = latest_play_by_link.get(link.id)
            completion_at = max(aware(first_passed.finalizada_em), aware(latest_play)) if latest_play else aware(first_passed.finalizada_em)
            completed_date = completion_at.astimezone(TZ).date()
            status = 'concluida_com_atraso' if due and completed_date > due else 'concluida_no_prazo' if due else 'concluida'
        elif due and today > due:
            status = 'atrasado'
        elif percent == 100 and not assessment:
            status = 'avaliacao_nao_configurada'
        elif not due:
            status = 'sem_prazo'
        elif percent == 100:
            status = 'aguardando_avaliacao'
        else:
            status = 'em_dia'
        assessment_view = None
        if assessment:
            assessment_view = dict(
                id=assessment.id, title=assessment.titulo, question_count=assessment.quantidade,
                content=assessment.conteudo, mode=assessment.formato, pass_score=assessment.nota_minima,
                attempts=len(sessions), best_score=best_session.pontuacao if best_session else None,
                passed=bool(first_passed), can_start=total > 0 and percent == 100,
            )
        detail = dict(**progress, status=status, status_label=labels[status],
                      due_date=due.isoformat() if due else None,
                      completed=completed, completed_at=completion_at.isoformat() if completion_at else None,
                      assessment=assessment_view)
        if include_attempts and assessment:
            detail['attempts'] = [dict(score=session.pontuacao, correct=session.corretas, total=session.total,
                                       passed=session.aprovada,
                                       played_at=aware(session.finalizada_em).astimezone(TZ).isoformat())
                                 for session in sorted(sessions, key=lambda session: aware(session.finalizada_em), reverse=True)[:10]]
        result[link.id] = detail
    return result


def _assessment_results_for_class(class_id, limit=100):
    rows = g.db.execute(select(AvaliacaoSessao, Usuario, Avaliacao, Trilha)
                        .join(Usuario, Usuario.id_usuario == AvaliacaoSessao.fk_usuario)
                        .join(Avaliacao, Avaliacao.id == AvaliacaoSessao.fk_avaliacao)
                        .join(TurmaTrilha, TurmaTrilha.id == Avaliacao.fk_turma_trilha)
                        .join(Trilha, Trilha.id_trilha == TurmaTrilha.fk_trilha)
                        .where(TurmaTrilha.fk_turma == class_id,
                               AvaliacaoSessao.finalizada_em.is_not(None))
                        .order_by(AvaliacaoSessao.finalizada_em.desc()).limit(limit)).all()
    return [dict(id=session.id, student=user.nome, student_id=str(user.id_usuario),
                 trail=trail.nome, assessment=assessment.titulo, score=session.pontuacao,
                 correct=session.corretas, total=session.total, passed=session.aprovada,
                 pass_score=session.nota_minima,
                 played_at=aware(session.finalizada_em).astimezone(TZ).isoformat())
            for session, user, assessment, trail in rows]


def _bulk_class_learning_status(student_ids, links):
    if not student_ids or not links:
        return {}
    link_ids = [link.id for link in links]
    trail_ids = list({link.fk_trilha for link in links})
    totals = dict(g.db.execute(select(TrilhaTermo.fk_trilha, func.count(func.distinct(TrilhaTermo.fk_termo)))
                               .where(TrilhaTermo.fk_trilha.in_(trail_ids))
                               .group_by(TrilhaTermo.fk_trilha)).all())
    played = {(uid, link_id): (count, last) for uid, link_id, count, last in g.db.execute(
        select(Progresso.fk_usuario, Progresso.fk_turma_trilha,
               func.count(func.distinct(Progresso.fk_termo)), func.max(Progresso.data_conclusao))
        .join(TurmaTrilha, TurmaTrilha.id == Progresso.fk_turma_trilha)
        .join(TrilhaTermo, and_(TrilhaTermo.fk_trilha == TurmaTrilha.fk_trilha,
                                TrilhaTermo.fk_termo == Progresso.fk_termo))
        .where(Progresso.fk_usuario.in_(student_ids), Progresso.fk_turma_trilha.in_(link_ids),
               Progresso.jogado.is_(True))
        .group_by(Progresso.fk_usuario, Progresso.fk_turma_trilha)
    ).all()}
    passed = {(uid, link_id): first_pass for uid, link_id, first_pass in g.db.execute(
        select(AvaliacaoSessao.fk_usuario, Avaliacao.fk_turma_trilha,
               func.min(AvaliacaoSessao.finalizada_em))
        .join(Avaliacao, Avaliacao.id == AvaliacaoSessao.fk_avaliacao)
        .where(Avaliacao.fk_turma_trilha.in_(link_ids),
               AvaliacaoSessao.fk_usuario.in_(student_ids),
               AvaliacaoSessao.finalizada_em.is_not(None),
               AvaliacaoSessao.aprovada.is_(True))
        .group_by(AvaliacaoSessao.fk_usuario, Avaliacao.fk_turma_trilha)
    ).all()}
    today = utcnow().astimezone(TZ).date()
    summary = {}
    for uid in student_ids:
        states = []
        for link in links:
            total = int(totals.get(link.fk_trilha, 0) or 0)
            count, latest_play = played.get((uid, link.id), (0, None))
            passed_at = passed.get((uid, link.id))
            complete = bool(total and count >= total and passed_at)
            completed_at = None
            if complete:
                latest_play, passed_at = aware(latest_play), aware(passed_at)
                completed_at = max(latest_play, passed_at) if latest_play else passed_at
            if complete:
                late = bool(link.data_limite and completed_at.astimezone(TZ).date() > link.data_limite)
                states.append('concluida_com_atraso' if late else 'concluida')
            elif link.data_limite and today > link.data_limite:
                states.append('atrasado')
            elif link.data_limite:
                states.append('em_dia')
            else:
                states.append('sem_prazo')
        late_count = sum(status in ('atrasado', 'concluida_com_atraso') for status in states)
        completed_states = {'concluida', 'concluida_com_atraso'}
        if states and all(status in completed_states for status in states):
            label = f'{late_count} concluída(s) com atraso' if late_count else 'Trilhas concluídas'
        elif late_count:
            label = f'{late_count} trilha(s) atrasada(s)'
        elif any(status == 'em_dia' for status in states):
            label = 'Em dia'
        elif states:
            label = 'Sem prazo definido'
        else:
            label = 'Sem trilhas atribuídas'
        summary[uid] = dict(trail_status=label, late_trails=late_count,
                            pending_trails=sum(status not in completed_states for status in states),
                            assigned_trails=len(states))
    return summary


def _class_metrics(class_row, daily_day):
    uid = g.user.id_usuario
    links = g.db.scalars(select(TurmaTrilha).where(TurmaTrilha.fk_turma == class_row.id_turma)).all()
    link_ids = [link.id for link in links]
    students = g.db.execute(select(Usuario, Matricula).join(Matricula, Matricula.fk_usuario == Usuario.id_usuario)
                            .where(Matricula.fk_turma == class_row.id_turma)).all()
    student_ids = [u.id_usuario for u, _ in students]
    points_all = {ident: 0 for ident in student_ids}
    points_today = {ident: 0 for ident in student_ids}
    day_start, day_end = _local_day_bounds(daily_day)
    def accumulate(statement, target):
        for ident, amount in g.db.execute(statement).all():
            target[ident] = target.get(ident, 0) + int(amount or 0)
    if link_ids:
        accumulate(select(Partida.fk_usuario, func.sum(Partida.xp)).where(
            Partida.fk_turma_trilha.in_(link_ids), Partida.respondida.is_(True)).group_by(Partida.fk_usuario), points_all)
        accumulate(select(Partida.fk_usuario, func.sum(Partida.xp)).where(
            Partida.fk_turma_trilha.in_(link_ids), Partida.respondida.is_(True),
            Partida.respondida_em >= day_start, Partida.respondida_em < day_end).group_by(Partida.fk_usuario), points_today)
    # Jogos feitos dentro da turma, mas fora de uma trilha, entram no ranking da turma.
    standalone = select(Partida.fk_usuario, func.sum(Partida.xp)).join(
        GameQuestion, GameQuestion.fk_partida == Partida.id).join(
        GameSession, GameSession.id == GameQuestion.fk_sessao).where(
        GameSession.fk_turma == class_row.id_turma, GameSession.fk_turma_trilha.is_(None),
        Partida.respondida.is_(True)).group_by(Partida.fk_usuario)
    accumulate(standalone, points_all)
    accumulate(standalone.where(Partida.respondida_em >= day_start, Partida.respondida_em < day_end), points_today)
    by_id = {u.id_usuario: u for u, _m in students}
    total_rank = [dict(user_id=str(ident), name=by_id[ident].nome, xp=points_all[ident], is_me=ident == uid)
                  for ident in student_ids]
    daily_rank = [dict(user_id=str(ident), name=by_id[ident].nome, xp=points_today[ident], is_me=ident == uid)
                  for ident in student_ids]
    total_rank.sort(key=lambda x: (-x['xp'], x['name'].casefold()))
    daily_rank.sort(key=lambda x: (-x['xp'], x['name'].casefold()))
    for index, row in enumerate(total_rank, 1): row['rank'] = index
    for index, row in enumerate(daily_rank, 1): row['rank'] = index
    teacher_students = []
    if g.user.perfil == 'Professor':
        learning_summary = _bulk_class_learning_status(student_ids, links)
        for user, _membership in students:
            last = aware(user.ultimo_acesso_em)
            teacher_students.append(dict(user_id=str(user.id_usuario), name=user.nome, email=user.email,
                                         total_xp=points_all.get(user.id_usuario, 0), daily_xp=points_today.get(user.id_usuario, 0),
                                         last_access=last.astimezone(TZ).isoformat() if last else None,
                                         **learning_summary.get(user.id_usuario, dict(trail_status='Sem trilhas atribuídas', late_trails=0, pending_trails=0, assigned_trails=0))))
        teacher_students.sort(key=lambda x: (-x['total_xp'], x['name'].casefold()))
    return dict(total=total_rank, daily=daily_rank, day=daily_day.isoformat(),
                students=teacher_students)


def _class_feed(class_row):
    links = g.db.scalars(select(TurmaTrilha.id).where(TurmaTrilha.fk_turma == class_row.id_turma)).all()
    items = []
    sessions = g.db.execute(select(GameSession, Usuario).join(Usuario, Usuario.id_usuario == GameSession.fk_usuario)
                            .where(GameSession.fk_turma == class_row.id_turma, GameSession.finalizada_em.is_not(None))
                            .order_by(GameSession.finalizada_em.desc()).limit(15)).all()
    for game, user in sessions:
        items.append(dict(student=user.nome.split()[0], game=game.jogo, correct=game.corretas,
                          total=game.total, score=game.pontuacao,
                          at=aware(game.finalizada_em).astimezone(TZ).isoformat() if game.finalizada_em else None))
    assessments = g.db.execute(select(AvaliacaoSessao, Usuario, Avaliacao, Trilha)
                               .join(Usuario, Usuario.id_usuario == AvaliacaoSessao.fk_usuario)
                               .join(Avaliacao, Avaliacao.id == AvaliacaoSessao.fk_avaliacao)
                               .join(TurmaTrilha, TurmaTrilha.id == Avaliacao.fk_turma_trilha)
                               .join(Trilha, Trilha.id_trilha == TurmaTrilha.fk_trilha)
                               .where(TurmaTrilha.fk_turma == class_row.id_turma,
                                      AvaliacaoSessao.finalizada_em.is_not(None))
                               .order_by(AvaliacaoSessao.finalizada_em.desc()).limit(15)).all()
    for attempt, user, assessment, trail in assessments:
        items.append(dict(student=user.nome.split()[0], game='avaliacao_trilha',
                          assessment=assessment.titulo, trail=trail.nome,
                          correct=attempt.corretas, total=attempt.total, score=attempt.pontuacao,
                          at=aware(attempt.finalizada_em).astimezone(TZ).isoformat()))
    if links:
        legacy = g.db.execute(select(Partida, Usuario).join(Usuario, Usuario.id_usuario == Partida.fk_usuario)
                              .where(Partida.fk_turma_trilha.in_(links), Partida.respondida.is_(True),
                                     ~Partida.id.in_(select(GameQuestion.fk_partida)))
                              .order_by(Partida.respondida_em.desc()).limit(15)).all()
        for part, user in legacy:
            items.append(dict(student=user.nome.split()[0], game=part.jogo, correct=1 if part.correto else 0,
                              total=1, score=100 if part.correto else 0,
                              at=aware(part.respondida_em).astimezone(TZ).isoformat() if part.respondida_em else None))
    items.sort(key=lambda x: x.get('at') or '', reverse=True)
    return items[:15]


@api.get('/classes/<int:class_id>')
@_require_user
def class_detail(class_id):
    row = _class_for_user(class_id)
    day_text = request.args.get('date', '')
    try:
        daily_day = datetime.strptime(day_text, '%Y-%m-%d').date() if day_text else utcnow().astimezone(TZ).date()
    except ValueError:
        _fail(400, 'Data inválida.')
    links = g.db.scalars(select(TurmaTrilha).where(TurmaTrilha.fk_turma == row.id_turma)).all()
    trail_ids = list({link.fk_trilha for link in links})
    trail_rows = g.db.scalars(select(Trilha).where(Trilha.id_trilha.in_(trail_ids))).all() if trail_ids else []
    trail_data = {item['id']: item for item in trail_views(g.db, trail_rows)}
    assessment_rows = g.db.scalars(select(Avaliacao).where(Avaliacao.fk_turma_trilha.in_([link.id for link in links]))).all() if links else []
    assessments = {item.fk_turma_trilha: dict(id=item.id, title=item.titulo, question_count=item.quantidade,
                                               content=item.conteudo, mode=item.formato, pass_score=item.nota_minima)
                  for item in assessment_rows}
    learning_by_link = _bulk_assignment_learning_status(g.user.id_usuario, links) if g.user.perfil == 'Aluno' else {}
    trails = []
    for link in links:
        item = trail_data.get(link.fk_trilha)
        if not item:
            continue
        item = dict(item)
        item.update(assignment_id=link.id,
                    due_date=link.data_limite.isoformat() if link.data_limite else None,
                    assessment=assessments.get(link.id))
        if g.user.perfil == 'Aluno':
            item.update(learning_by_link.get(link.id, {}))
            item['progress'] = item.get('percent', 0)
        trails.append(item)
    metrics = _class_metrics(row, daily_day)
    result = dict(id=row.id_turma, name=row.nome, role=g.user.perfil, code=row.codigo if g.user.perfil == 'Professor' else None,
                  trails=trails, leaderboard=metrics['total'], daily_leaderboard=metrics['daily'],
                  daily_date=metrics['day'])
    if g.user.perfil == 'Professor':
        result['students'] = metrics['students']
        result['assessment_results'] = _assessment_results_for_class(row.id_turma)
        own_trails = g.db.scalars(select(Trilha).where(Trilha.fk_professor == g.user.id_usuario).order_by(Trilha.nome)).all()
        result['available_trails'] = trail_views(g.db, own_trails)
    else:
        # O feed da turma só é carregado ao abrir a página daquela turma.
        result['feed'] = _class_feed(row)
    return jsonify(**result)


@api.get('/classes/<int:class_id>/students/<student_id>')
@_teacher
def class_student_detail(class_id, student_id):
    class_row = owned_class(g.db, g.user.id_usuario, class_id)
    user = g.db.get(Usuario, student_id)
    enrolled = g.db.scalar(select(Matricula.id).where(
        Matricula.fk_turma == class_row.id_turma,
        Matricula.fk_usuario == student_id,
    ))
    if not user or user.perfil != 'Aluno' or not enrolled:
        _fail(404, 'Aluno não encontrado nesta turma.')
    day = utcnow().astimezone(TZ).date()
    metrics = _class_metrics(class_row, day)
    summary = next((item for item in metrics['students'] if item['user_id'] == str(user.id_usuario)), None)
    links = g.db.scalars(select(TurmaTrilha).where(TurmaTrilha.fk_turma == class_row.id_turma)
                         .order_by(TurmaTrilha.id)).all()
    trail_ids = list({link.fk_trilha for link in links})
    trails_by_id = {trail.id_trilha: trail for trail in g.db.scalars(
        select(Trilha).where(Trilha.id_trilha.in_(trail_ids))
    ).all()} if trail_ids else {}
    learning_by_link = _bulk_assignment_learning_status(user.id_usuario, links, include_attempts=True)
    trails = []
    for link in links:
        trail = trails_by_id.get(link.fk_trilha)
        if not trail:
            continue
        details = learning_by_link.get(link.id, {})
        attempts = details.pop('attempts', [])
        trails.append(dict(assignment_id=link.id, trail_id=trail.id_trilha, name=trail.nome,
                           area=trail.area or 'Todas as áreas', **details, attempts=attempts))
    return jsonify(student=dict(user_id=str(user.id_usuario), name=user.nome, email=user.email,
                                last_access=aware(user.ultimo_acesso_em).astimezone(TZ).isoformat() if user.ultimo_acesso_em else None,
                                total_xp=summary['total_xp'] if summary else 0,
                                daily_xp=summary['daily_xp'] if summary else 0),
                   class_id=class_row.id_turma, class_name=class_row.nome, trails=trails)


def _trail_data(trail, uid, assignment_id=None):
    result = trail_views(g.db, [trail])[0]
    if assignment_id:
        link = assignment(g.db, g.user, assignment_id)
        if link.fk_trilha != trail.id_trilha:
            _fail(404, 'Trilha não encontrada.')
        result['assignment_id'] = link.id
        result['class_id'] = link.fk_turma
        result['progress'] = progress_percent(g.db, uid, link)
    terms = g.db.scalars(visible_terms(uid).join(TrilhaTermo, TrilhaTermo.fk_termo == Termo.id_termo)
                         .where(TrilhaTermo.fk_trilha == trail.id_trilha).order_by(Termo.palavra_completa)).all()
    result['term_items'] = _term_data(terms, uid)
    return result


@api.get('/trails/<int:trail_id>')
@_require_user
def trail_detail(trail_id):
    trail = g.db.get(Trilha, trail_id)
    if not trail:
        _fail(404, 'Trilha não encontrada.')
    link_id = request.args.get('assignment_id')
    if g.user.perfil == 'Professor':
        if trail.fk_professor != g.user.id_usuario:
            _fail(404, 'Trilha não encontrada.')
    elif not link_id:
        _fail(404, 'Trilha não encontrada.')
    return jsonify(trail=_trail_data(trail, g.user.id_usuario, _positive_int(link_id) if link_id else None))


def _bind_trail(class_row, trail):
    link = g.db.scalar(select(TurmaTrilha).where(TurmaTrilha.fk_turma == class_row.id_turma,
                                                  TurmaTrilha.fk_trilha == trail.id_trilha))
    if not link:
        link = TurmaTrilha(fk_turma=class_row.id_turma, fk_trilha=trail.id_trilha)
        g.db.add(link)
        g.db.flush()
    terms = g.db.scalars(select(Termo).join(TrilhaTermo, TrilhaTermo.fk_termo == Termo.id_termo)
                         .where(TrilhaTermo.fk_trilha == trail.id_trilha)).all()
    for term in terms:
        if term.criado_pelo_professor:
            if term.criado_por != g.user.id_usuario:
                _fail(403, 'A trilha contém um termo privado de outro professor.')
            exists = g.db.scalar(select(TermoTurma.id).where(TermoTurma.fk_termo == term.id_termo,
                                                              TermoTurma.fk_turma == class_row.id_turma))
            if not exists:
                g.db.add(TermoTurma(fk_termo=term.id_termo, fk_turma=class_row.id_turma))
    return link


@api.get('/catalog/terms')
@_require_user
def catalog_terms():
    query = visible_terms(g.user.id_usuario)
    area = request.args.get('area', '').strip()
    search = request.args.get('search', '').strip()[:150]
    if area:
        query = query.join(Area).where(Area.nome == area)
    if search:
        query = query.where(func.lower(Termo.palavra_completa).contains(search.lower(), autoescape=True))
    rows = g.db.scalars(query.order_by(Termo.palavra_completa).limit(500)).all()
    return jsonify(terms=_term_data(rows, g.user.id_usuario), count=len(rows))


@api.get('/catalog/radicals')
@_require_user
def catalog_radicals():
    rows = g.db.scalars(_visible_radicals(g.user.id_usuario).order_by(Radical.nome).limit(1000)).all()
    _, favorites = _favorite_ids(g.user.id_usuario)
    return jsonify(radicals=_radical_data(rows, g.user.id_usuario, favorites))


@api.post('/trails')
@_teacher
def trail_create():
    data = _body()
    name = _field(data.get('name', ''), 'nome da trilha', 150)
    description = _field(data.get('description', ''), 'descrição', 3000, False)
    area = _field(data.get('area', ''), 'área', 100, False)
    term_ids = list(dict.fromkeys(_positive_int(x, 'termo') for x in data.get('term_ids', []) if str(x).isdigit()))
    if not term_ids or len(term_ids) > 500:
        _fail(400, 'Selecione ao menos um termo para a trilha.')
    for term_id in term_ids:
        visible_term(g.db, g.user.id_usuario, term_id)
    classes = list(dict.fromkeys(_positive_int(x, 'turma') for x in data.get('class_ids', []) if str(x).isdigit()))
    for class_id in classes:
        owned_class(g.db, g.user.id_usuario, class_id)
    trail = Trilha(nome=name, descricao=description, area=area, fk_professor=g.user.id_usuario)
    g.db.add(trail)
    g.db.flush()
    g.db.add_all([TrilhaTermo(fk_trilha=trail.id_trilha, fk_termo=term_id) for term_id in term_ids])
    g.db.flush()
    due_date = _parse_date(data.get('due_date'), 'prazo')
    for class_id in classes:
        link = _bind_trail(g.db.get(Turma, class_id), trail)
        link.data_limite = due_date
    g.db.commit()
    return jsonify(trail=_trail_data(trail, g.user.id_usuario), message='Trilha criada.'), 201


@api.delete('/trails/<int:trail_id>')
@_teacher
def trail_delete(trail_id):
    trail = owned_trail(g.db, g.user.id_usuario, trail_id)
    g.db.delete(trail)
    g.db.commit()
    return jsonify(message='Trilha apagada.')


@api.post('/classes/<int:class_id>/trails')
@_teacher
def class_assign_trail(class_id):
    data = _body()
    class_row = owned_class(g.db, g.user.id_usuario, class_id)
    trail = owned_trail(g.db, g.user.id_usuario, _positive_int(data.get('trail_id'), 'trilha'))
    link = _bind_trail(class_row, trail)
    link.data_limite = _parse_date(data.get('due_date'), 'prazo')
    g.db.commit()
    return jsonify(assignment_id=link.id, message='Trilha atribuída à turma.'), 201


@api.delete('/classes/<int:class_id>/trails/<int:trail_id>')
@_teacher
def class_unassign_trail(class_id, trail_id):
    class_row = owned_class(g.db, g.user.id_usuario, class_id)
    link = g.db.scalar(select(TurmaTrilha).where(TurmaTrilha.fk_turma == class_row.id_turma,
                                                 TurmaTrilha.fk_trilha == trail_id))
    if not link:
        _fail(404, 'Trilha não encontrada nesta turma.')
    g.db.delete(link)
    g.db.commit()
    return jsonify(message='Trilha removida da turma.')


@api.post('/classes/<int:class_id>/trails/<int:assignment_id>/assessment')
@_teacher
def assessment_upsert(class_id, assignment_id):
    class_row = owned_class(g.db, g.user.id_usuario, class_id)
    link = g.db.scalar(select(TurmaTrilha).where(
        TurmaTrilha.id == assignment_id,
        TurmaTrilha.fk_turma == class_row.id_turma,
    ))
    if not link:
        _fail(404, 'Trilha não encontrada nesta turma.')
    trail = owned_trail(g.db, g.user.id_usuario, link.fk_trilha)
    data = _body()
    title = _field(data.get('title') or f'Avaliação: {trail.nome}', 'título', 150)
    try:
        count = int(data.get('question_count', 10))
        pass_score = int(data.get('pass_score', 70))
    except (TypeError, ValueError):
        _fail(400, 'Quantidade ou nota mínima inválida.')
    if not 1 <= count <= 50 or not 0 <= pass_score <= 100:
        _fail(400, 'A avaliação aceita de 1 a 50 questões e nota mínima de 0 a 100.')
    content = str(data.get('content', 'ambos'))
    mode = str(data.get('mode', 'misto'))
    if content not in ('termos', 'radicais', 'ambos'):
        _fail(400, 'Escolha termos, radicais ou os dois conteúdos.')
    if mode not in ('misto', 'termo_definicao', 'definicao_termo', 'radical_significado', 'significado_radical'):
        _fail(400, 'Formato da avaliação inválido.')
    if content == 'termos' and mode in ('radical_significado', 'significado_radical'):
        _fail(400, 'Esse formato exige conteúdo de radicais.')
    if content == 'radicais' and mode in ('termo_definicao', 'definicao_termo'):
        _fail(400, 'Esse formato exige conteúdo de termos.')
    row = g.db.scalar(select(Avaliacao).where(Avaliacao.fk_turma_trilha == link.id))
    if not row:
        row = Avaliacao(fk_turma_trilha=link.id, fk_professor=g.user.id_usuario)
        g.db.add(row)
    row.titulo, row.quantidade = title, count
    row.conteudo, row.formato, row.nota_minima = content, mode, pass_score
    g.db.commit()
    return jsonify(assessment=_assessment_config(link), message='Avaliação salva para esta turma e trilha.')


@api.post('/classes/<int:class_id>/trails/<int:assignment_id>/assessment/sessions')
@_student
def assessment_start(class_id, assignment_id):
    link = assignment(g.db, g.user, assignment_id)
    if link.fk_turma != class_id:
        _fail(404, 'Avaliação não encontrada nesta turma.')
    assessment = g.db.scalar(select(Avaliacao).where(Avaliacao.fk_turma_trilha == link.id))
    if not assessment:
        _fail(404, 'O professor ainda não configurou a avaliação desta trilha.')
    learning = progress_detail(g.db, g.user.id_usuario, link)
    if not learning['total'] or learning['percent'] != 100:
        _fail(409, 'Pratique cada termo da trilha pelo menos uma vez antes de iniciar a avaliação.')
    pool = _assessment_question_pool(g.user.id_usuario, link, assessment)
    questions = pool[:assessment.quantidade]
    if not questions:
        _fail(400, 'Não há questões suficientes para montar esta avaliação. Avise o professor para revisar os termos e radicais da trilha.')
    session_id = str(uuid.uuid4())
    session = AvaliacaoSessao(id=session_id, fk_avaliacao=assessment.id,
                              fk_usuario=g.user.id_usuario, total=len(questions),
                              nota_minima=assessment.nota_minima)
    g.db.add(session)
    output = []
    for position, item in enumerate(questions, 1):
        question_id = str(uuid.uuid4())
        g.db.add(AvaliacaoQuestao(id=question_id, fk_sessao=session_id, posicao=position,
                                  fk_termo=item['term_id'], fk_radical=item['radical_id'],
                                  prompt=item['prompt'], opcoes=item['options'],
                                  resposta_esperada=item['expected']))
        output.append(dict(id=question_id, prompt=item['prompt'], options=item['options']))
    g.db.commit()
    return jsonify(session_id=session_id, title=assessment.titulo, total=len(output),
                   pass_score=session.nota_minima, questions=output), 201


@api.post('/assessment/sessions/<session_id>/answer')
@_student
def assessment_answer(session_id):
    data = _body()
    question_id = str(data.get('question_id', ''))
    session = g.db.scalar(select(AvaliacaoSessao).where(
        AvaliacaoSessao.id == session_id,
        AvaliacaoSessao.fk_usuario == g.user.id_usuario,
    ).with_for_update())
    if not session:
        _fail(404, 'Avaliação não encontrada.')
    if session.finalizada_em:
        _fail(409, 'Esta avaliação já foi finalizada.')
    question = g.db.scalar(select(AvaliacaoQuestao).where(
        AvaliacaoQuestao.id == question_id,
        AvaliacaoQuestao.fk_sessao == session.id,
    ).with_for_update())
    if not question:
        _fail(404, 'Questão não encontrada nesta avaliação.')
    if question.respondida:
        return jsonify(correct=bool(question.correta), answer=next(
            (option['label'] for option in question.opcoes if option['id'] == question.resposta_esperada), ''),
            correct_count=session.corretas, total=session.total)
    choice = data.get('answer')
    if not isinstance(choice, str) or len(choice) > 100:
        _fail(400, 'Selecione uma alternativa válida.')
    if not any(option['id'] == choice for option in question.opcoes):
        _fail(400, 'A alternativa não pertence a esta questão.')
    question.respondida = True
    question.correta = secrets.compare_digest(choice, question.resposta_esperada)
    session.corretas += int(question.correta)
    g.db.flush()
    correct_label = next((option['label'] for option in question.opcoes
                          if option['id'] == question.resposta_esperada), '')
    g.db.commit()
    return jsonify(correct=bool(question.correta), answer=correct_label,
                   correct_count=session.corretas, total=session.total)


@api.post('/assessment/sessions/<session_id>/finish')
@_student
def assessment_finish(session_id):
    session = g.db.scalar(select(AvaliacaoSessao).where(
        AvaliacaoSessao.id == session_id,
        AvaliacaoSessao.fk_usuario == g.user.id_usuario,
    ).with_for_update())
    if not session:
        _fail(404, 'Avaliação não encontrada.')
    if not session.finalizada_em:
        unanswered = g.db.scalar(select(func.count(AvaliacaoQuestao.id)).where(
            AvaliacaoQuestao.fk_sessao == session.id,
            AvaliacaoQuestao.respondida.is_(False),
        )) or 0
        if unanswered:
            _fail(409, 'Responda todas as questões antes de finalizar.')
        session.pontuacao = round(100 * session.corretas / session.total) if session.total else 0
        session.aprovada = session.pontuacao >= session.nota_minima
        session.finalizada_em = utcnow()
    g.db.commit()
    return jsonify(session_id=session.id, score=session.pontuacao, correct=session.corretas,
                   total=session.total, pass_score=session.nota_minima, passed=session.aprovada,
                   finished_at=aware(session.finalizada_em).isoformat())


@api.post('/terms')
@_teacher
def teacher_term_create():
    data = _body()
    name = _field(data.get('name', ''), 'palavra', 200)
    definition = _field(data.get('definition', ''), 'definição', 5000)
    area_id = _positive_int(data.get('area_id'), 'área')
    if not g.db.get(Area, area_id):
        _fail(400, 'Área não encontrada.')
    class_ids = list(dict.fromkeys(_positive_int(x, 'turma') for x in data.get('class_ids', []) if str(x).isdigit()))
    trail_ids = list(dict.fromkeys(_positive_int(x, 'trilha') for x in data.get('trail_ids', []) if str(x).isdigit()))
    if not class_ids and not trail_ids:
        _fail(400, 'Escolha ao menos uma turma ou trilha para compartilhar este termo.')
    for class_id in class_ids:
        owned_class(g.db, g.user.id_usuario, class_id)
    trails = [owned_trail(g.db, g.user.id_usuario, trail_id) for trail_id in trail_ids]
    pieces = data.get('radicals', [])
    if not isinstance(pieces, list) or not 1 <= len(pieces) <= 10:
        _fail(400, 'Informe entre 1 e 10 radicais.')
    term = Termo(palavra_completa=name, definicao_biologica=definition, fk_area=area_id,
                 criado_por=g.user.id_usuario, criado_pelo_professor=True)
    g.db.add(term)
    g.db.flush()
    for order, piece in enumerate(pieces, 1):
        radical_name = _field(piece.get('name', ''), 'radical', 100)
        meaning = _field(piece.get('meaning', ''), 'significado do radical', 500)
        classification = str(piece.get('classification', '')).upper()
        if classification not in ('PREFIXO', 'RADICAL', 'SUFIXO'):
            _fail(400, 'Classifique o radical como PREFIXO, RADICAL ou SUFIXO.')
        radical = Radical(nome=radical_name, significado=meaning, classificacao=classification, fk_area=area_id)
        g.db.add(radical)
        g.db.flush()
        g.db.add(TermoRadical(fk_termo=term.id_termo, fk_radical=radical.id_radical, ordem=order))
    g.db.add_all([TermoTurma(fk_termo=term.id_termo, fk_turma=i) for i in class_ids])
    for trail in trails:
        g.db.add(TrilhaTermo(fk_trilha=trail.id_trilha, fk_termo=term.id_termo))
        assigned_classes = g.db.scalars(select(Turma).join(TurmaTrilha, TurmaTrilha.fk_turma == Turma.id_turma)
                                        .where(TurmaTrilha.fk_trilha == trail.id_trilha)).all()
        for class_row in assigned_classes:
            exists = g.db.scalar(select(TermoTurma.id).where(TermoTurma.fk_termo == term.id_termo,
                                                              TermoTurma.fk_turma == class_row.id_turma))
            if not exists:
                g.db.add(TermoTurma(fk_termo=term.id_termo, fk_turma=class_row.id_turma))
    g.db.commit()
    return jsonify(term=_term_data([term], g.user.id_usuario)[0]), 201


@api.post('/me/terms')
@_student
def student_term_create():
    data = _body()
    name = _field(data.get('name', ''), 'palavra', 200)
    definition = _field(data.get('definition', ''), 'definição', 5000)
    area_id = _positive_int(data.get('area_id'), 'área') if data.get('area_id') else None
    if area_id and not g.db.get(Area, area_id):
        _fail(400, 'Área não encontrada.')
    radical_ids = list(dict.fromkeys(_positive_int(x, 'radical') for x in data.get('radical_ids', []) if str(x).isdigit()))
    if not 1 <= len(radical_ids) <= 10:
        _fail(400, 'Escolha entre 1 e 10 radicais do banco.')
    radicals = g.db.scalars(_visible_radicals(g.user.id_usuario).where(Radical.id_radical.in_(radical_ids))).all()
    if len(radicals) != len(radical_ids):
        _fail(400, 'Um dos radicais selecionados não está disponível.')
    term = Termo(palavra_completa=name, definicao_biologica=definition, fk_area=area_id,
                 criado_por=g.user.id_usuario, criado_pelo_professor=True)
    g.db.add(term)
    g.db.flush()
    g.db.add_all([TermoRadical(fk_termo=term.id_termo, fk_radical=rad.id_radical, ordem=index)
                  for index, rad in enumerate(radicals, 1)])
    collection_id = data.get('collection_id')
    if collection_id:
        collection = g.db.scalar(select(Colecao).where(Colecao.id == _positive_int(collection_id, 'coleção'),
                                                        Colecao.fk_usuario == g.user.id_usuario))
        if not collection:
            _fail(404, 'Coleção não encontrada.')
        g.db.flush()
        g.db.add(ColecaoTermo(fk_colecao=collection.id, fk_termo=term.id_termo))
    g.db.commit()
    return jsonify(term=_term_data([term], g.user.id_usuario)[0]), 201


def _explore_terms(area='', search='', favorite=False):
    query = visible_terms(g.user.id_usuario)
    if area:
        query = query.join(Area).where(Area.nome == area)
    if search:
        query = query.where(or_(func.lower(Termo.palavra_completa).contains(search.lower(), autoescape=True),
                                func.lower(Termo.definicao_biologica).contains(search.lower(), autoescape=True)))
    favorite_ids, _ = _favorite_ids(g.user.id_usuario)
    if favorite:
        query = query.where(Termo.id_termo.in_(favorite_ids))
    terms = g.db.scalars(query.order_by(func.lower(Termo.palavra_completa)).limit(1000)).all()
    return _term_data(terms, g.user.id_usuario, favorite_ids)


def _explore_radicals(area='', search='', favorite=False):
    query = _visible_radicals(g.user.id_usuario)
    if area:
        query = query.join(Area, Area.id_area == Radical.fk_area).where(Area.nome == area)
    if search:
        query = query.where(or_(func.lower(Radical.nome).contains(search.lower(), autoescape=True),
                                func.lower(Radical.significado).contains(search.lower(), autoescape=True)))
    _, favorite_ids = _favorite_ids(g.user.id_usuario)
    if favorite:
        query = query.where(Radical.id_radical.in_(favorite_ids))
    rows = g.db.scalars(query.order_by(func.lower(Radical.nome)).limit(1000)).all()
    return _radical_data(rows, g.user.id_usuario, favorite_ids)


@api.get('/explore')
@_require_user
def explore():
    kind = request.args.get('kind', 'both')
    if kind not in ('terms', 'radicals', 'both', 'favorites'):
        _fail(400, 'Tipo de conteúdo inválido.')
    area = request.args.get('area', '').strip()
    search = request.args.get('search', '').strip()[:150]
    favorite = kind == 'favorites'
    terms = _explore_terms(area, search, favorite) if kind in ('terms', 'both', 'favorites') else []
    radicals = _explore_radicals(area, search, favorite) if kind in ('radicals', 'both', 'favorites') else []
    return jsonify(kind=kind, terms=terms, radicals=radicals,
                   areas=[a.nome for a in g.db.scalars(select(Area).order_by(Area.nome))])


@api.get('/explore/terms/<int:term_id>')
@_require_user
def explore_term(term_id):
    term = visible_term(g.db, g.user.id_usuario, term_id)
    view = _term_data([term], g.user.id_usuario)[0]
    radical_ids = [r['radical_id'] for r in view['radical_list']]
    related = []
    if radical_ids:
        terms = g.db.scalars(visible_terms(g.user.id_usuario).join(TermoRadical, TermoRadical.fk_termo == Termo.id_termo)
                             .where(TermoRadical.fk_radical.in_(radical_ids), Termo.id_termo != term_id)
                             .distinct().order_by(Termo.palavra_completa).limit(30)).all()
        related = _term_data(terms, g.user.id_usuario)
    return jsonify(term=view, similar_terms=related)


@api.get('/explore/radicals/<int:radical_id>')
@_require_user
def explore_radical(radical_id):
    radical = _visible_radical(g.user.id_usuario, radical_id)
    view = _radical_data([radical], g.user.id_usuario)[0]
    terms = g.db.scalars(visible_terms(g.user.id_usuario).join(TermoRadical, TermoRadical.fk_termo == Termo.id_termo)
                         .where(TermoRadical.fk_radical == radical_id).distinct()
                         .order_by(Termo.palavra_completa).limit(100)).all()
    return jsonify(radical=view, terms=_term_data(terms, g.user.id_usuario))


@api.get('/favorites')
@_require_user
def favorites_list():
    return jsonify(terms=_explore_terms(favorite=True), radicals=_explore_radicals(favorite=True))


@api.post('/favorites')
@_require_user
def favorite_add():
    data = _body()
    kind, ident = data.get('type'), _positive_int(data.get('id'))
    if kind == 'term':
        visible_term(g.db, g.user.id_usuario, ident)
        row = g.db.scalar(select(FavoritoTermo).where(FavoritoTermo.fk_usuario == g.user.id_usuario,
                                                      FavoritoTermo.fk_termo == ident))
        if not row: g.db.add(FavoritoTermo(fk_usuario=g.user.id_usuario, fk_termo=ident))
    elif kind == 'radical':
        _visible_radical(g.user.id_usuario, ident)
        row = g.db.scalar(select(FavoritoRadical).where(FavoritoRadical.fk_usuario == g.user.id_usuario,
                                                        FavoritoRadical.fk_radical == ident))
        if not row: g.db.add(FavoritoRadical(fk_usuario=g.user.id_usuario, fk_radical=ident))
    else:
        _fail(400, 'Tipo de favorito inválido.')
    g.db.commit()
    return jsonify(message='Adicionado aos favoritos.')


@api.delete('/favorites/<kind>/<int:ident>')
@_require_user
def favorite_remove(kind, ident):
    if kind == 'term':
        visible_term(g.db, g.user.id_usuario, ident)
        g.db.execute(delete(FavoritoTermo).where(FavoritoTermo.fk_usuario == g.user.id_usuario,
                                                  FavoritoTermo.fk_termo == ident))
    elif kind == 'radical':
        _visible_radical(g.user.id_usuario, ident)
        g.db.execute(delete(FavoritoRadical).where(FavoritoRadical.fk_usuario == g.user.id_usuario,
                                                    FavoritoRadical.fk_radical == ident))
    else:
        _fail(400, 'Tipo de favorito inválido.')
    g.db.commit()
    return jsonify(message='Removido dos favoritos.')


def _collection_or_404(ident):
    collection = g.db.scalar(select(Colecao).where(Colecao.id == ident, Colecao.fk_usuario == g.user.id_usuario))
    if not collection: _fail(404, 'Coleção não encontrada.')
    return collection


def _collection_data(collection):
    terms = g.db.scalars(visible_terms(g.user.id_usuario).join(ColecaoTermo, ColecaoTermo.fk_termo == Termo.id_termo)
                         .where(ColecaoTermo.fk_colecao == collection.id).order_by(Termo.palavra_completa)).all()
    return dict(id=collection.id, name=collection.nome, created_at=aware(collection.criada_em).isoformat(),
                terms=_term_data(terms, g.user.id_usuario))


@api.get('/collections')
@_student
def collections_list():
    rows = g.db.scalars(select(Colecao).where(Colecao.fk_usuario == g.user.id_usuario).order_by(Colecao.criada_em.desc())).all()
    return jsonify(collections=[_collection_data(row) for row in rows])


@api.post('/collections')
@_student
def collection_create():
    data = _body()
    name = _field(data.get('name', ''), 'nome da coleção', 100)
    ids = list(dict.fromkeys(_positive_int(x, 'termo') for x in data.get('term_ids', []) if str(x).isdigit()))
    if len(ids) > 500: _fail(400, 'A coleção pode ter até 500 termos.')
    for ident in ids: visible_term(g.db, g.user.id_usuario, ident)
    collection = Colecao(fk_usuario=g.user.id_usuario, nome=name)
    g.db.add(collection)
    g.db.flush()
    g.db.add_all([ColecaoTermo(fk_colecao=collection.id, fk_termo=ident) for ident in ids])
    g.db.commit()
    return jsonify(collection=_collection_data(collection)), 201


@api.get('/collections/<int:collection_id>')
@_student
def collection_detail(collection_id):
    return jsonify(collection=_collection_data(_collection_or_404(collection_id)))


@api.delete('/collections/<int:collection_id>')
@_student
def collection_delete(collection_id):
    g.db.delete(_collection_or_404(collection_id))
    g.db.commit()
    return jsonify(message='Coleção apagada.')


@api.post('/collections/<int:collection_id>/terms')
@_student
def collection_add_terms(collection_id):
    collection = _collection_or_404(collection_id)
    data = _body()
    ids = data.get('term_ids', [data.get('term_id')])
    if not isinstance(ids, list): _fail(400, 'Informe os termos selecionados.')
    ids = list(dict.fromkeys(_positive_int(x, 'termo') for x in ids if str(x).isdigit()))
    if not ids: _fail(400, 'Selecione ao menos um termo.')
    for ident in ids:
        visible_term(g.db, g.user.id_usuario, ident)
        exists = g.db.scalar(select(ColecaoTermo.id).where(ColecaoTermo.fk_colecao == collection.id,
                                                           ColecaoTermo.fk_termo == ident))
        if not exists: g.db.add(ColecaoTermo(fk_colecao=collection.id, fk_termo=ident))
    g.db.commit()
    return jsonify(collection=_collection_data(collection))


@api.delete('/collections/<int:collection_id>/terms/<int:term_id>')
@_student
def collection_remove_term(collection_id, term_id):
    collection = _collection_or_404(collection_id)
    g.db.execute(delete(ColecaoTermo).where(ColecaoTermo.fk_colecao == collection.id,
                                             ColecaoTermo.fk_termo == term_id))
    g.db.commit()
    return jsonify(message='Termo removido da coleção.')


@api.get('/sources')
@_student
def practice_sources():
    class_links = g.db.execute(select(TurmaTrilha, Turma, Trilha).join(Turma, Turma.id_turma == TurmaTrilha.fk_turma)
                               .join(Trilha, Trilha.id_trilha == TurmaTrilha.fk_trilha)
                               .join(Matricula, Matricula.fk_turma == Turma.id_turma)
                               .where(Matricula.fk_usuario == g.user.id_usuario).order_by(Turma.nome, Trilha.nome)).all()
    trails = [dict(assignment_id=link.id, trail_id=trail.id_trilha, name=trail.nome, area=trail.area,
                   class_id=class_row.id_turma, class_name=class_row.nome)
              for link, class_row, trail in class_links]
    collections = g.db.scalars(select(Colecao).where(Colecao.fk_usuario == g.user.id_usuario).order_by(Colecao.nome)).all()
    term_favs, radical_favs = _favorite_ids(g.user.id_usuario)
    return jsonify(areas=[dict(id=a.id_area, name=a.nome) for a in g.db.scalars(select(Area).order_by(Area.nome))],
                   trails=trails, collections=[dict(id=c.id, name=c.nome) for c in collections],
                   favorites_count=len(term_favs) + len(radical_favs))


@api.get('/trails/<int:trail_id>/terms')
@_require_user
def trail_terms(trail_id):
    trail = g.db.get(Trilha, trail_id)
    if not trail: _fail(404, 'Trilha não encontrada.')
    link_id = request.args.get('assignment_id')
    if g.user.perfil == 'Aluno':
        if not link_id: _fail(404, 'Trilha não encontrada.')
        link = assignment(g.db, g.user, _positive_int(link_id, 'trilha'))
        if link.fk_trilha != trail_id: _fail(404, 'Trilha não encontrada.')
    elif trail.fk_professor != g.user.id_usuario:
        _fail(404, 'Trilha não encontrada.')
    terms = g.db.scalars(visible_terms(g.user.id_usuario).join(TrilhaTermo, TrilhaTermo.fk_termo == Termo.id_termo)
                         .where(TrilhaTermo.fk_trilha == trail_id).order_by(Termo.palavra_completa)).all()
    return jsonify(terms=_term_data(terms, g.user.id_usuario))


def _source_terms(user, data):
    source_type = str(data.get('source_type', 'area'))
    source_id = data.get('source_id')
    class_id = _positive_int(data.get('class_id'), 'turma') if data.get('class_id') else None
    link_id = None
    query = visible_terms(user.id_usuario)
    if source_type == 'area':
        area = _field(data.get('area', ''), 'área', 100)
        query = query.join(Area).where(Area.nome == area)
    elif source_type == 'trail':
        link_id = _positive_int(source_id, 'trilha')
        link = assignment(g.db, user, link_id)
        if class_id and link.fk_turma != class_id: _fail(403, 'Trilha não pertence à turma escolhida.')
        class_id = link.fk_turma
        trail = g.db.get(Trilha, link.fk_trilha)
        source_id = link.id
        query = query.join(TrilhaTermo, TrilhaTermo.fk_termo == Termo.id_termo).where(TrilhaTermo.fk_trilha == trail.id_trilha)
    elif source_type == 'collection':
        collection = _collection_or_404(_positive_int(source_id, 'coleção'))
        source_id = collection.id
        query = query.join(ColecaoTermo, ColecaoTermo.fk_termo == Termo.id_termo).where(ColecaoTermo.fk_colecao == collection.id)
    elif source_type == 'favorites':
        term_ids, radical_ids = _favorite_ids(user.id_usuario)
        related = select(TermoRadical.fk_termo).where(TermoRadical.fk_radical.in_(radical_ids)) if radical_ids else select(Termo.id_termo).where(False)
        ids = set(term_ids) | set(g.db.scalars(related))
        query = query.where(Termo.id_termo.in_(ids))
        source_id = None
    else:
        _fail(400, 'Escolha uma área, trilha, coleção ou favoritos.')
    if class_id:
        _class_for_user(class_id)
    rows = g.db.scalars(query.distinct().order_by(Termo.palavra_completa).limit(1000)).all()
    if not rows:
        _fail(400, 'Não há termos disponíveis nessa seleção.')
    return rows, source_type, source_id, class_id, link_id


def _clean_radicals(term_view):
    return [r for r in term_view.get('radical_list', []) if r.get('text', '').strip() and r.get('meaning', '').strip()]


def _make_questions(game, views, source_id=None, count=10, mode='termo_definicao'):
    rng = random.SystemRandom()
    by_id = {v['id']: v for v in views}
    ids = list(by_id)
    if game == 'familia_palavras':
        pool = rng.sample(ids, min(20, len(ids)))
        counts = {}
        for ident in pool:
            for radical in _clean_radicals(by_id[ident]): counts.setdefault(radical['radical_id'], []).append(ident)
        eligible = [(rid, terms) for rid, terms in counts.items() if len(set(terms)) >= 2]
        rng.shuffle(eligible)
        if len(eligible) < 2: _fail(400, 'Esta seleção precisa ter ao menos dois radicais compartilhados entre termos.')
        questions = []
        for index, (rid, correct_ids) in enumerate(eligible[:5]):
            radical = next(r for term_id in correct_ids for r in _clean_radicals(by_id[term_id]) if r['radical_id'] == rid)
            target = rng.choice(correct_ids)
            options = [dict(id=ident, name=by_id[ident]['name']) for ident in pool]
            rng.shuffle(options)
            questions.append((target, sorted(set(correct_ids)), dict(
                kind=game, prompt=radical['meaning'], _radical=radical['text'],
                _radical_id=rid, _coverage_terms=pool, options=options,
                instruction='Selecione todos os termos relacionados.')))
        return questions
    if game == 'memoria':
        mode = mode if mode in ('termo_definicao', 'radical_significado') else 'termo_definicao'
        pairs = []
        memory_radical_ids = []
        requested = int(count)
        pair_count = min((6, 8, 10), key=lambda option: abs(option - requested))
        if mode == 'termo_definicao':
            for ident in rng.sample(ids, min(pair_count, len(ids))):
                pairs.append((by_id[ident]['name'], by_id[ident]['definition'], ident))
        else:
            unique = {}
            for ident in ids:
                for rad in _clean_radicals(by_id[ident]):
                    entry = unique.setdefault(rad['radical_id'], dict(text=rad['text'], meaning=rad['meaning'], term_ids=[]))
                    entry['term_ids'].append(ident)
            selected_roots = rng.sample(list(unique.items()), min(pair_count, len(unique)))
            for radical_id, entry in selected_roots:
                pairs.append((entry['text'], entry['meaning'], entry['term_ids'][0]))
                memory_radical_ids.append(radical_id)
        if len(pairs) < 2: _fail(400, 'Não há pares suficientes para este modo de memória.')
        cards, expected, coverage_map = [], [], {}
        for pair_index, (left, right, ident) in enumerate(pairs):
            a, b = secrets.token_urlsafe(10), secrets.token_urlsafe(10)
            cards.extend([dict(id=a, text=left), dict(id=b, text=right)])
            expected.append(sorted([a, b]))
            if mode == 'termo_definicao':
                related_ids = [ident]
            else:
                related_ids = list(dict.fromkeys(unique[memory_radical_ids[pair_index]]['term_ids']))
            coverage_map[a] = related_ids
            coverage_map[b] = related_ids
        rng.shuffle(cards)
        return [(pairs[0][2], expected, dict(kind=game, mode=mode, cards=cards,
                                             radical_ids=memory_radical_ids,
                                             _coverage_map=coverage_map,
                                             instruction='Encontre todos os pares.'))]
    if game == 'decifrador':
        questions = []
        for ident in rng.sample(ids, min(max(1, count), len(ids))):
            term = by_id[ident]
            letters = list(term['name'].upper().replace(' ', ''))
            rng.shuffle(letters)
            questions.append((ident, normalize(term['name']), dict(kind=game, clue=term['definition'], letters=letters,
                                                                   radicals=_clean_radicals(term), _coverage_terms=[ident])))
        return questions
    if game == 'flashcard':
        unlocked = g.db.scalars(select(Flashcard).where(Flashcard.fk_usuario == g.user.id_usuario,
                                                       Flashcard.ativo.is_(True),
                                                       Flashcard.fk_termo.in_(ids),
                                                       or_(Flashcard.proxima_revisao_em.is_(None), Flashcard.proxima_revisao_em <= utcnow()))
                                .order_by(Flashcard.proxima_revisao_em).limit(max(1, count))).all()
        if not unlocked: _fail(400, 'Você ainda não tem flashcards vencidos nessa seleção. Acerte um jogo para desbloquear cartões.')
        questions = []
        for card in unlocked:
            term = by_id.get(card.fk_termo)
            if term: questions.append((term['id'], {'card_id': card.id_flashcard}, dict(kind=game, term_name=term['name'], definition=term['definition'], radicals=_clean_radicals(term), card_id=card.id_flashcard, _coverage_terms=[term['id']])))
        return questions
    _fail(400, 'Jogo inválido.')


@api.post('/games/sessions')
@_student
def game_start():
    data = _body()
    game = str(data.get('game', ''))
    if game not in ('decifrador', 'familia_palavras', 'memoria', 'flashcard'):
        _fail(400, 'Jogo inválido.')
    try:
        count = max(1, min(30, int(data.get('question_count', 10))))
    except (TypeError, ValueError):
        count = 10
    rows, source_type, source_id, class_id, link_id = _source_terms(g.user, data)
    views = _term_data(rows, g.user.id_usuario)
    questions = _make_questions(game, views, source_id, count, str(data.get('mode', 'termo_definicao')))
    if not questions: _fail(400, 'Não há perguntas suficientes nessa seleção.')
    session_id = str(uuid.uuid4())
    game_session = GameSession(id=session_id, fk_usuario=g.user.id_usuario, fk_turma=class_id,
                               fk_turma_trilha=link_id, jogo=game, source_type=source_type,
                               source_id=source_id, total=len(questions))
    g.db.add(game_session)
    g.db.flush()
    payloads = []
    for position, (term_id, expected, payload) in enumerate(questions, 1):
        partida = Partida(id=str(uuid.uuid4()), fk_usuario=g.user.id_usuario, fk_termo=term_id,
                          fk_turma_trilha=link_id, jogo=game, resposta_esperada=expected)
        g.db.add(partida)
        g.db.flush()
        g.db.add(GameQuestion(fk_sessao=session_id, fk_partida=partida.id, posicao=position, payload=payload))
        payloads.append(dict(id=partida.id, **{key: value for key, value in payload.items() if not key.startswith('_')}))
    g.db.commit()
    return jsonify(session_id=session_id, game=game, questions=payloads,
                   total=len(payloads), source_type=source_type), 201


def _answer_equal(game, expected, answer):
    if game == 'familia_palavras':
        if not isinstance(answer, list) or len(answer) > 500:
            return False
        try:
            parsed = [int(value) for value in answer if not isinstance(value, bool)]
            if len(parsed) != len(answer) or len(set(parsed)) != len(parsed):
                return False
            return set(parsed) == set(map(int, expected))
        except (TypeError, ValueError): return False
    if game == 'memoria':
        if not isinstance(answer, list) or len(answer) > 20:
            return False
        try:
            if any(not isinstance(pair, list) or len(pair) != 2 or
                   not all(isinstance(value, str) for value in pair) or pair[0] == pair[1]
                   for pair in answer):
                return False
            pairs = sorted(sorted(str(v) for v in pair) for pair in answer)
            if len({tuple(pair) for pair in pairs}) != len(pairs):
                return False
            return pairs == sorted(sorted(str(v) for v in pair) for pair in expected)
        except TypeError: return False
    if game == 'decifrador':
        return isinstance(answer, str) and normalize(answer) == expected
    if game == 'flashcard':
        return isinstance(answer, bool) and answer
    return False


def _favorite_feedback(term_ids, radical_ids):
    term_ids = list(dict.fromkeys(int(x) for x in term_ids))
    radical_ids = list(dict.fromkeys(int(x) for x in radical_ids))
    favorite_terms, favorite_radicals = _favorite_ids(g.user.id_usuario)
    terms = g.db.scalars(visible_terms(g.user.id_usuario).where(Termo.id_termo.in_(term_ids))).all() if term_ids else []
    radicals = g.db.scalars(_visible_radicals(g.user.id_usuario).where(Radical.id_radical.in_(radical_ids))) if radical_ids else []
    return dict(
        favorite_terms=[dict(id=t.id_termo, name=t.palavra_completa, favorite=t.id_termo in favorite_terms) for t in terms],
        favorite_radicals=[dict(id=r.id_radical, name=r.nome, meaning=r.significado,
                                favorite=r.id_radical in favorite_radicals) for r in radicals],
    )


def _feedback(partida, payload, correct, answer=None):
    term = visible_term(g.db, g.user.id_usuario, partida.fk_termo)
    term_view = term_views(g.db, [term])[0]
    term_ids = [partida.fk_termo]
    radical_ids = [r['radical_id'] for r in term_view['radical_list']]
    feedback = {}
    if partida.jogo == 'familia_palavras':
        expected_ids = {int(x) for x in partida.resposta_esperada}
        term_ids = list(expected_ids)
        radical_ids = [int(payload['_radical_id'])]
        terms = g.db.scalars(visible_terms(g.user.id_usuario).where(Termo.id_termo.in_(term_ids))).all()
        names = {t.id_termo: t.palavra_completa for t in terms}
        submitted = payload.get('_last_answer', []) if answer is None else answer
        try:
            selected_ids = {int(value) for value in submitted}
        except (TypeError, ValueError):
            selected_ids = set()
        feedback.update(
            correct_terms=[names[ident] for ident in sorted(expected_ids) if ident in names],
            correct_selected=[names[ident] for ident in sorted(expected_ids & selected_ids) if ident in names],
            omitted_terms=[names[ident] for ident in sorted(expected_ids - selected_ids) if ident in names],
            incorrect_terms=[names[ident] for ident in sorted(selected_ids - expected_ids) if ident in names],
        )
        feedback['radical'] = payload['_radical']
    elif partida.jogo == 'memoria':
        cards = {x['id']: x['text'] for x in payload['cards']}
        feedback['correct_pairs'] = [[cards[a], cards[b]] for a, b in partida.resposta_esperada]
        radical_ids = payload.get('radical_ids') or radical_ids
    elif partida.jogo == 'decifrador':
        feedback['correct_answer'] = term.palavra_completa
    elif partida.jogo == 'flashcard':
        feedback['correct_answer'] = term.definicao_biologica
    feedback.update(_favorite_feedback(term_ids, radical_ids))
    return feedback


@api.post('/games/sessions/<session_id>/answer')
@_student
def game_answer(session_id):
    data = _body()
    question_id = str(data.get('question_id', ''))
    session_row = g.db.scalar(select(GameSession).where(GameSession.id == session_id,
                                                        GameSession.fk_usuario == g.user.id_usuario).with_for_update())
    if not session_row: _fail(404, 'Partida não encontrada.')
    if session_row.finalizada_em: _fail(409, 'Esta partida já terminou.')
    question = g.db.scalar(select(GameQuestion).where(GameQuestion.fk_sessao == session_id,
                                                      GameQuestion.fk_partida == question_id))
    partida = g.db.scalar(select(Partida).where(Partida.id == question_id, Partida.fk_usuario == g.user.id_usuario).with_for_update())
    if not question or not partida: _fail(404, 'Questão não encontrada.')
    if partida.respondida:
        return jsonify(correct=bool(partida.correto), xp=partida.xp, feedback=_feedback(partida, question.payload, bool(partida.correto)))
    if aware(partida.criada_em) < utcnow() - timedelta(hours=2): _fail(400, 'Esta partida expirou. Inicie outra.')
    visible_term(g.db, g.user.id_usuario, partida.fk_termo)
    if session_row.source_type == 'trail' and not session_row.fk_turma_trilha:
        _fail(400, 'A trilha foi apagada. Inicie outra prática.')
    if session_row.fk_turma_trilha:
        link = assignment(g.db, g.user, session_row.fk_turma_trilha)
        if not g.db.scalar(select(TrilhaTermo.id).where(TrilhaTermo.fk_trilha == link.fk_trilha,
                                                       TrilhaTermo.fk_termo == partida.fk_termo)):
            _fail(400, 'A trilha mudou. Inicie uma nova partida.')
    elif session_row.fk_turma:
        _class_for_user(session_row.fk_turma)
    answer = data.get('answer')
    if partida.jogo == 'familia_palavras':
        options = question.payload.get('options', [])
        valid_ids = {int(option['id']) for option in options if isinstance(option, dict) and str(option.get('id', '')).isdigit()}
        if (not isinstance(answer, list) or len(answer) > len(valid_ids) or
                any(isinstance(value, bool) or not str(value).isdigit() for value in answer)):
            _fail(400, 'Seleção de termos inválida.')
        answer = [int(value) for value in answer]
        if len(set(answer)) != len(answer) or not set(answer).issubset(valid_ids):
            _fail(400, 'Seleção de termos inválida.')
    elif partida.jogo == 'memoria':
        expected_pairs = {tuple(sorted(str(x) for x in pair)) for pair in partida.resposta_esperada}
        recorded_pairs = question.payload.get('_matched_pairs', [])
        valid_pairs = {tuple(sorted(str(x) for x in pair)) for pair in recorded_pairs
                       if isinstance(pair, list) and len(pair) == 2}
        if valid_pairs != expected_pairs:
            _fail(409, 'Encontre todos os pares antes de continuar.')
        answer = [list(pair) for pair in valid_pairs]
    if partida.jogo == 'flashcard':
        value = data.get('remembered')
        if not isinstance(value, bool): _fail(400, 'Resposta inválida.')
        answer = value
        card = g.db.scalar(select(Flashcard).where(Flashcard.id_flashcard == partida.resposta_esperada['card_id'],
                                                 Flashcard.fk_usuario == g.user.id_usuario, Flashcard.ativo.is_(True)).with_for_update())
        if not card: _fail(404, 'Flashcard não encontrado.')
        card.dificuldade = 'fácil' if answer else 'difícil'
        card.proxima_revisao_em = utcnow() + (timedelta(days=3) if answer else timedelta(hours=1))
    correct = _answer_equal(partida.jogo, partida.resposta_esperada, answer)
    save_result(g.db, g.user, partida, correct)
    if partida.jogo == 'familia_palavras':
        question.payload = {**question.payload, '_last_answer': answer if isinstance(answer, list) else []}
    if session_row.fk_turma_trilha:
        coverage = question.payload.get('_coverage_terms', [])
        if partida.jogo == 'familia_palavras':
            _mark_practiced_terms(g.user.id_usuario, session_row.fk_turma_trilha, coverage)
        else:
            _mark_practiced_terms(g.user.id_usuario, session_row.fk_turma_trilha, [partida.fk_termo])
    if correct and session_row.fk_turma and not session_row.fk_turma_trilha:
        enrollment = g.db.scalar(select(Matricula).where(Matricula.fk_usuario == g.user.id_usuario,
                                                         Matricula.fk_turma == session_row.fk_turma))
        if enrollment: enrollment.pontuacao = (enrollment.pontuacao or 0) + (partida.xp or 0)
    session_row.corretas += int(correct)
    session_row.xp += partida.xp or 0
    g.db.flush()
    feedback = _feedback(partida, question.payload, correct, answer)
    if correct:
        term = visible_term(g.db, g.user.id_usuario, partida.fk_termo)
        if partida.jogo != 'flashcard':
            flashcard = g.db.scalar(select(Flashcard).where(Flashcard.fk_usuario == g.user.id_usuario,
                                                           Flashcard.fk_termo == term.id_termo))
            feedback['flashcard_unlocked'] = bool(flashcard)
    g.db.commit()
    return jsonify(correct=correct, xp=partida.xp, feedback=feedback,
                   correct_count=session_row.corretas, total=session_row.total)


@api.post('/games/sessions/<session_id>/match')
@_student
def game_memory_match(session_id):
    data = _body()
    question_id = str(data.get('question_id', ''))
    pair = data.get('pair', [])
    if not isinstance(pair, list) or len(pair) != 2 or not all(isinstance(x, str) for x in pair):
        _fail(400, 'Selecione dois cartões.')
    session_row = g.db.scalar(select(GameSession).where(GameSession.id == session_id,
                                                        GameSession.fk_usuario == g.user.id_usuario).with_for_update())
    question = g.db.scalar(select(GameQuestion).where(GameQuestion.fk_sessao == session_id,
                                                      GameQuestion.fk_partida == question_id).with_for_update())
    if not session_row or not question or session_row.jogo != 'memoria':
        _fail(404, 'Partida de memória não encontrada.')
    if session_row.finalizada_em:
        _fail(409, 'Esta partida já terminou.')
    if aware(session_row.criada_em) < utcnow() - timedelta(hours=2):
        _fail(400, 'Esta partida expirou. Inicie outra.')
    valid_ids = {card['id'] for card in question.payload['cards']}
    if pair[0] not in valid_ids or pair[1] not in valid_ids or pair[0] == pair[1]:
        _fail(400, 'Cartões inválidos.')
    partida = g.db.get(Partida, question_id)
    if not partida or partida.fk_usuario != g.user.id_usuario or partida.respondida:
        _fail(404, 'Cartões indisponíveis.')
    expected_pairs = {tuple(sorted(str(x) for x in expected)) for expected in partida.resposta_esperada}
    question.payload = {**question.payload,
                        'attempt_count': int(question.payload.get('attempt_count', 0)) + 1}
    matched = tuple(sorted(pair)) in expected_pairs
    if matched and session_row.fk_turma_trilha:
        covered = set()
        for card_id in pair:
            covered.update(question.payload.get('_coverage_map', {}).get(card_id, []))
        _mark_practiced_terms(g.user.id_usuario, session_row.fk_turma_trilha, covered)
    if matched:
        normalized_pair = list(sorted(pair))
        recorded = question.payload.get('_matched_pairs', [])
        if normalized_pair not in recorded:
            question.payload = {**question.payload, '_matched_pairs': [*recorded, normalized_pair]}
    g.db.commit()
    return jsonify(match=matched, attempts=question.payload['attempt_count'])


@api.post('/games/sessions/<session_id>/finish')
@_student
def game_finish(session_id):
    row = g.db.scalar(select(GameSession).where(GameSession.id == session_id,
                                                GameSession.fk_usuario == g.user.id_usuario).with_for_update())
    if not row: _fail(404, 'Partida não encontrada.')
    if not row.finalizada_em:
        unanswered = g.db.scalar(select(func.count(Partida.id)).join(GameQuestion, GameQuestion.fk_partida == Partida.id)
                                 .where(GameQuestion.fk_sessao == session_id, Partida.respondida.is_(False))) or 0
        if unanswered: _fail(409, 'Responda todas as questões antes de finalizar.')
        row.finalizada_em = utcnow()
        row.pontuacao = round(100 * row.corretas / row.total) if row.total else 0
        g.db.commit()
    return jsonify(session_id=row.id, score=row.pontuacao, correct=row.corretas,
                   total=row.total, xp=row.xp, finished_at=aware(row.finalizada_em).isoformat())
