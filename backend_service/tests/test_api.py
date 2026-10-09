import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import create_app
from backend.demo import ALUNO_ID, seed
from backend.models import (AvaliacaoQuestao, Base, GameSession, Partida, Turma,
                            TurmaTrilha, Usuario)


@pytest.fixture
def app():
    app = create_app({
        'TESTING': True,
        'DEMO_MODE': True,
        'DATABASE_URL': 'sqlite:///:memory:',
        'SECRET_KEY': 'test-secret-with-more-than-thirty-two-characters',
        'FRONTEND_ORIGINS': 'https://lise.example',
        'FRONTEND_URL': 'https://lise.example',
    })
    Base.metadata.create_all(app.extensions['engine'])
    with Session(app.extensions['engine']) as db:
        seed(db)
        db.commit()
    return app


def login(client, email='aluno@lise.demo'):
    response = client.post('/api/v1/auth/login', json={'email': email, 'password': 'LiseDemo123!'})
    assert response.status_code == 200, response.json
    return {'Authorization': f"Bearer {response.json['access_token']}"}


def test_auth_cors_private_terms_and_no_isolated_term_practice(app):
    client = app.test_client()
    assert client.get('/api/v1/classes').status_code == 401
    headers = login(client)
    response = client.get('/api/v1/explore?kind=both', headers={**headers, 'Origin': 'https://lise.example'})
    assert response.status_code == 200
    assert response.headers['Access-Control-Allow-Origin'] == 'https://lise.example'
    assert len(response.json['terms']) == 7
    created = client.post('/api/v1/me/terms', headers=headers, json={
        'name': 'Palavra pessoal', 'definition': 'Termo criado pela aluna.', 'area_id': 1, 'radical_ids': [1, 2]})
    assert created.status_code == 201
    term_id = created.json['term']['id']
    collection = client.post('/api/v1/collections', headers=headers,
                             json={'name': 'Minha coleção', 'term_ids': [term_id]})
    assert collection.status_code == 201
    assert collection.json['collection']['terms'][0]['created_by_me'] is True
    isolated = client.post('/api/v1/games/sessions', headers=headers, json={
        'game': 'decifrador', 'source_type': 'term', 'source_id': term_id})
    assert isolated.status_code == 400
    with Session(app.extensions['engine']) as db:
        other_id = str(uuid.uuid4())
        db.add(Usuario(id_usuario=other_id, nome='Outra aluna', email='outra@lise.demo', perfil='Aluno'))
        db.commit()
    other = app.test_client()
    other_headers = login(other, 'outra@lise.demo')
    terms = other.get('/api/v1/catalog/terms', headers=other_headers).json['terms']
    assert term_id not in [item['id'] for item in terms]


def test_montagem_and_quiz_are_not_practice_games_and_memory_supports_pair_counts(app):
    student = app.test_client()
    headers = login(student)
    for removed_game in ('montagem', 'bioquiz'):
        response = student.post('/api/v1/games/sessions', headers=headers, json={
            'game': removed_game, 'source_type': 'area', 'area': 'Biologia Geral'})
        assert response.status_code == 400
    started = student.post('/api/v1/games/sessions', headers=headers, json={
        'game': 'memoria', 'source_type': 'area', 'area': 'Biologia Geral',
        'mode': 'termo_definicao', 'question_count': 6})
    assert started.status_code == 201, started.json
    question = started.json['questions'][0]
    assert len(question['cards']) == 12
    assert '_coverage_map' not in question


def test_family_options_are_validated_and_memory_requires_server_recorded_matches(app):
    student = app.test_client()
    headers = login(student)
    family = student.post('/api/v1/games/sessions', headers=headers, json={
        'game': 'familia_palavras', 'source_type': 'area', 'area': 'Biologia Geral'})
    assert family.status_code == 201, family.json
    family_question = family.json['questions'][0]
    invalid = student.post(f"/api/v1/games/sessions/{family.json['session_id']}/answer",
                           headers=headers,
                           json={'question_id': family_question['id'], 'answer': [999999]})
    assert invalid.status_code == 400

    memory = student.post('/api/v1/games/sessions', headers=headers, json={
        'game': 'memoria', 'source_type': 'area', 'area': 'Biologia Geral',
        'mode': 'termo_definicao', 'question_count': 6})
    assert memory.status_code == 201, memory.json
    memory_question = memory.json['questions'][0]
    with Session(app.extensions['engine']) as db:
        expected = db.get(Partida, memory_question['id']).resposta_esperada
    forged = student.post(f"/api/v1/games/sessions/{memory.json['session_id']}/answer",
                          headers=headers,
                          json={'question_id': memory_question['id'], 'answer': expected})
    assert forged.status_code == 409

    for pair in expected:
        matched = student.post(f"/api/v1/games/sessions/{memory.json['session_id']}/match",
                               headers=headers,
                               json={'question_id': memory_question['id'], 'pair': pair})
        assert matched.status_code == 200 and matched.json['match'] is True
    submitted = student.post(f"/api/v1/games/sessions/{memory.json['session_id']}/answer",
                             headers=headers,
                             json={'question_id': memory_question['id'], 'answer': []})
    assert submitted.status_code == 200 and submitted.json['correct'] is True


def test_trail_requires_practice_of_every_term_then_teacher_assessment(app):
    teacher = app.test_client()
    teacher_headers = login(teacher, 'professor@lise.demo')
    trail = teacher.post('/api/v1/trails', headers=teacher_headers, json={
        'name': 'Trilha de teste', 'term_ids': [1, 2, 3], 'class_ids': [1],
        'due_date': (datetime.now(timezone.utc) + timedelta(days=7)).date().isoformat()})
    assert trail.status_code == 201, trail.json
    trail_id = trail.json['trail']['id']
    with Session(app.extensions['engine']) as db:
        assignment_id = db.scalar(select(TurmaTrilha.id).where(TurmaTrilha.fk_trilha == trail_id))
    config = teacher.post(f'/api/v1/classes/1/trails/{assignment_id}/assessment', headers=teacher_headers, json={
        'title': 'Avaliação de etimologia', 'question_count': 6, 'content': 'ambos', 'mode': 'misto', 'pass_score': 70})
    assert config.status_code == 200, config.json

    student = app.test_client()
    student_headers = login(student)
    blocked = student.post(f'/api/v1/classes/1/trails/{assignment_id}/assessment/sessions',
                           headers=student_headers, json={})
    assert blocked.status_code == 409

    practice = student.post('/api/v1/games/sessions', headers=student_headers, json={
        'game': 'decifrador', 'source_type': 'trail', 'source_id': assignment_id, 'question_count': 3})
    assert practice.status_code == 201, practice.json
    for question in practice.json['questions']:
        response = student.post(f"/api/v1/games/sessions/{practice.json['session_id']}/answer",
                                headers=student_headers,
                                json={'question_id': question['id'], 'answer': 'resposta errada'})
        assert response.status_code == 200 and response.json['correct'] is False
    student.post(f"/api/v1/games/sessions/{practice.json['session_id']}/finish",
                 headers=student_headers, json={})
    class_detail = student.get('/api/v1/classes/1', headers=student_headers).json
    trail_view = next(item for item in class_detail['trails'] if item['assignment_id'] == assignment_id)
    assert trail_view['played'] == 3
    assert trail_view['progress'] == 100
    assert trail_view['assessment']['can_start'] is True

    assessment = student.post(f'/api/v1/classes/1/trails/{assignment_id}/assessment/sessions',
                              headers=student_headers, json={})
    assert assessment.status_code == 201, assessment.json
    for question in assessment.json['questions']:
        with Session(app.extensions['engine']) as db:
            expected = db.get(AvaliacaoQuestao, question['id']).resposta_esperada
        answer = student.post(f"/api/v1/assessment/sessions/{assessment.json['session_id']}/answer",
                              headers=student_headers,
                              json={'question_id': question['id'], 'answer': expected})
        assert answer.status_code == 200 and answer.json['correct'] is True
    finished = student.post(f"/api/v1/assessment/sessions/{assessment.json['session_id']}/finish",
                            headers=student_headers, json={})
    assert finished.status_code == 200 and finished.json['passed'] is True
    assert finished.json['score'] == 100

    report = teacher.get('/api/v1/classes/1', headers=teacher_headers)
    assert report.status_code == 200
    assert any(item['score'] == 100 for item in report.json['assessment_results'])
    assert report.json['students'][0]['last_access'] is not None
    details = teacher.get(f'/api/v1/classes/1/students/{ALUNO_ID}', headers=teacher_headers)
    assert details.status_code == 200
    own_assignment = next(item for item in details.json['trails'] if item['assignment_id'] == assignment_id)
    assert own_assignment['completed'] is True
    assert own_assignment['attempts'][0]['score'] == 100


def test_student_trail_details_are_scoped_to_the_selected_class_and_feed_is_limited(app):
    teacher = app.test_client()
    teacher_headers = login(teacher, 'professor@lise.demo')
    second_class = teacher.post('/api/v1/classes', headers=teacher_headers, json={'name': 'Outra turma'})
    assert second_class.status_code == 201
    class_id = second_class.json['id']
    student = app.test_client()
    student_headers = login(student)
    joined = student.post('/api/v1/classes/join', headers=student_headers,
                          json={'code': second_class.json['code']})
    assert joined.status_code == 200
    second_trail = teacher.post('/api/v1/trails', headers=teacher_headers, json={
        'name': 'Trilha da segunda turma', 'term_ids': [4, 5], 'class_ids': [class_id]})
    assert second_trail.status_code == 201
    first_detail = teacher.get(f'/api/v1/classes/1/students/{ALUNO_ID}', headers=teacher_headers).json
    assert all(item['name'] != 'Trilha da segunda turma' for item in first_detail['trails'])
    second_detail = teacher.get(f'/api/v1/classes/{class_id}/students/{ALUNO_ID}', headers=teacher_headers).json
    assert [item['name'] for item in second_detail['trails']] == ['Trilha da segunda turma']

    with Session(app.extensions['engine']) as db:
        now = datetime.now(timezone.utc)
        for index in range(20):
            db.add(GameSession(id=str(uuid.uuid4()), fk_usuario=ALUNO_ID, fk_turma=1,
                               jogo='decifrador', source_type='area', source_id=1, total=1,
                               corretas=1, xp=15, pontuacao=100,
                               criada_em=now-timedelta(minutes=index+1),
                               finalizada_em=now-timedelta(minutes=index+1)))
        db.commit()
    opened_class = student.get('/api/v1/classes/1', headers=student_headers)
    assert opened_class.status_code == 200
    assert len(opened_class.json['feed']) == 15


def test_teacher_registration_needs_invite_code():
    class AuthStub:
        def __init__(self):
            self.auth = self

        def sign_up(self, _payload):
            return None

    auth = AuthStub()
    app = create_app({
        'TESTING': True,
        'DEMO_MODE': False,
        'DATABASE_URL': 'sqlite:///:memory:',
        'SECRET_KEY': 'test-secret-with-more-than-thirty-two-characters',
        'TEACHER_INVITE_CODE': 'code-for-test-only',
        'AUTH_FACTORY': lambda: auth,
    })
    Base.metadata.create_all(app.extensions['engine'])
    client = app.test_client()
    payload = {'name': 'Professora', 'email': 'prof@lise.test', 'password': 'SenhaForte123', 'role': 'PROFESSOR'}
    assert client.post('/api/v1/auth/register', json=payload).status_code == 403
    payload['teacher_code'] = 'code-for-test-only'
    assert client.post('/api/v1/auth/register', json=payload).status_code == 201
