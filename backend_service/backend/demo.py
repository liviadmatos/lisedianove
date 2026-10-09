"""Dados fictícios locais. Nunca importa ou altera contas reais do Supabase."""
import uuid
from sqlalchemy import select
from .models import *

PROFESSOR_ID = '11111111-1111-4111-8111-111111111111'
ALUNO_ID = '22222222-2222-4222-8222-222222222222'


def seed(db):
    if db.scalar(select(Usuario.id_usuario)):
        return
    db.add_all([
        Usuario(id_usuario=PROFESSOR_ID, nome='Professora Demonstração', email='professor@lise.demo', perfil='Professor'),
        Usuario(id_usuario=ALUNO_ID, nome='Aluno Demonstração', email='aluno@lise.demo', perfil='Aluno'),
    ])
    db.flush()
    area = Area(nome='Citologia')
    general = Area(nome='Biologia Geral')
    db.add_all([area, general]); db.flush()
    examples = [
        ('Biologia', 'Ciência que estuda a vida e os seres vivos.', [('bio','vida','RADICAL'),('logia','estudo','SUFIXO')], general),
        ('Bioma', 'Conjunto de ecossistemas com clima, vegetação e fauna característicos.', [('bio','vida','RADICAL'),('oma','conjunto','SUFIXO')], general),
        ('Citologia', 'Área da biologia que estuda as células.', [('cito','célula','RADICAL'),('logia','estudo','SUFIXO')], area),
        ('Citoplasma', 'Material que preenche o interior da célula entre a membrana e o núcleo.', [('cito','célula','RADICAL'),('plasma','substância formada','RADICAL')], area),
        ('Histologia', 'Estudo dos tecidos dos seres vivos.', [('histo','tecido','RADICAL'),('logia','estudo','SUFIXO')], general),
        ('Fotossíntese', 'Processo em que a energia luminosa é convertida em energia química para produzir matéria orgânica.', [('foto','luz','RADICAL'),('síntese','composição, formação','RADICAL')], general),
        ('Autótrofo', 'Organismo que produz matéria orgânica a partir de substâncias inorgânicas.', [('auto','por si mesmo','PREFIXO'),('trofo','nutrição','RADICAL')], general),
    ]
    terms = []
    radical_index = {}
    for name, definition, pieces, a in examples:
        term = Termo(palavra_completa=name, definicao_biologica=definition, fk_area=a.id_area)
        db.add(term); db.flush(); terms.append(term)
        for i, (part, meaning, kind) in enumerate(pieces, 1):
            key = (part.casefold(), meaning.casefold(), kind)
            rad = radical_index.get(key)
            if not rad:
                rad = Radical(nome=part, significado=meaning, classificacao=kind, fk_area=a.id_area)
                db.add(rad); db.flush(); radical_index[key] = rad
            db.add(TermoRadical(fk_termo=term.id_termo, fk_radical=rad.id_radical, ordem=i))
    turma = Turma(nome='Biologia — demonstração', codigo='LISE26', fk_professor=PROFESSOR_ID)
    trilha = Trilha(nome='Primeiras descobertas', fk_professor=PROFESSOR_ID, descricao='Explore a etimologia de cinco termos.', area='Biologia Geral')
    db.add_all([turma, trilha]); db.flush()
    db.add(Matricula(fk_usuario=ALUNO_ID, fk_turma=turma.id_turma))
    db.add_all([TrilhaTermo(fk_trilha=trilha.id_trilha, fk_termo=t.id_termo) for t in terms])
    db.add(TurmaTrilha(fk_turma=turma.id_turma, fk_trilha=trilha.id_trilha))
