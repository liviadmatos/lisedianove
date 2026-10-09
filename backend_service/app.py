"""Aplicação Flask de API JSON; não serve templates nem arquivos do frontend."""
import os
import hashlib
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, g, jsonify, redirect, request
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from supabase import create_client, ClientOptions
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from backend.models import Sessao, Usuario
from backend.rest_api import api
from backend.services import aware, utcnow

load_dotenv(Path(__file__).resolve().parent / '.env')


def create_app(config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.getenv('SECRET_KEY'),
        DATABASE_URL=os.getenv('DATABASE_URL'),
        SUPABASE_URL=os.getenv('SUPABASE_URL'),
        SUPABASE_PUBLISHABLE_KEY=os.getenv('SUPABASE_PUBLISHABLE_KEY'),
        TEACHER_INVITE_CODE=os.getenv('TEACHER_INVITE_CODE', ''),
        FRONTEND_URL=os.getenv('FRONTEND_URL', 'http://127.0.0.1:5500').strip().rstrip('/'),
        FRONTEND_ORIGINS=os.getenv('FRONTEND_ORIGINS', 'http://127.0.0.1:5500,http://localhost:5500,http://localhost:5173'),
        DEMO_MODE=os.getenv('DEMO_MODE', 'false').lower() == 'true',
        PROXY_HOPS=int(os.getenv('PROXY_HOPS', '0')),
        MAX_CONTENT_LENGTH=128 * 1024,
    )
    if config:
        app.config.update(config)
    if not app.config['SECRET_KEY'] or len(app.config['SECRET_KEY']) < 32:
        raise RuntimeError('Defina SECRET_KEY com pelo menos 32 caracteres.')
    if not app.config['DATABASE_URL']:
        raise RuntimeError('Defina DATABASE_URL.')
    if not app.testing and not app.config['DEMO_MODE']:
        if not app.config['SUPABASE_URL'] or not app.config['SUPABASE_PUBLISHABLE_KEY']:
            raise RuntimeError('Defina SUPABASE_URL e SUPABASE_PUBLISHABLE_KEY.')

    db_url = app.config['DATABASE_URL']
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql+psycopg://', 1)
    elif db_url.startswith('postgresql://'):
        db_url = db_url.replace('postgresql://', 'postgresql+psycopg://', 1)
    engine_args = {'pool_pre_ping': True}
    if db_url.startswith('sqlite'):
        engine_args['connect_args'] = {'check_same_thread': False}
        if ':memory:' in db_url:
            engine_args['poolclass'] = StaticPool
    else:
        # Vercel runs short-lived functions. Reuse at most one connection per warm
        # instance; transaction-pooler mode and disabled prepared statements fit this runtime.
        engine_args.update(pool_size=1, max_overflow=0, pool_timeout=5, pool_recycle=1200,
                           connect_args={'sslmode': 'require', 'connect_timeout': 8, 'prepare_threshold': None})
    engine = create_engine(db_url, **engine_args)
    if db_url.startswith('sqlite'):
        @event.listens_for(engine, 'connect')
        def sqlite_fk(connection, _record):
            connection.execute('PRAGMA foreign_keys=ON')
    app.extensions['engine'] = engine

    def auth_client():
        factory = app.config.get('AUTH_FACTORY')
        if factory:
            return factory()
        return create_client(app.config['SUPABASE_URL'], app.config['SUPABASE_PUBLISHABLE_KEY'],
                             options=ClientOptions(persist_session=False, auto_refresh_token=False))
    app.extensions['lise_auth_client'] = auth_client

    if app.config['PROXY_HOPS']:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=app.config['PROXY_HOPS'], x_proto=app.config['PROXY_HOPS'])

    @app.before_request
    def load_bearer_user():
        g.user = None
        if request.method == 'OPTIONS' and request.path.startswith('/api/v1/'):
            return
        g.db = Session(engine)
        header = request.headers.get('Authorization', '')
        token = header[7:].strip() if header.lower().startswith('bearer ') else ''
        if not token:
            return
        row = g.db.get(Sessao, hashlib.sha256(token.encode()).hexdigest())
        if row and aware(row.expira_em) > utcnow():
            g.user = g.db.get(Usuario, row.fk_usuario)

    @app.teardown_request
    def close_database(_error=None):
        db = g.pop('db', None)
        if db:
            db.close()

    @app.after_request
    def secure_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Cache-Control'] = 'no-store'
        if request.path.startswith('/api/v1/'):
            origin = request.headers.get('Origin')
            allowed = {item.strip().rstrip('/') for item in app.config['FRONTEND_ORIGINS'].split(',') if item.strip()}
            if origin and origin.rstrip('/') in allowed:
                response.headers['Access-Control-Allow-Origin'] = origin
                response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PATCH, DELETE, OPTIONS'
                response.headers['Access-Control-Allow-Headers'] = 'Authorization, Content-Type'
                response.headers['Access-Control-Max-Age'] = '600'
                response.headers.add('Vary', 'Origin')
        return response

    @app.get('/')
    def root():
        return redirect(app.config['FRONTEND_URL'] + '/', code=302)

    @app.get('/healthz')
    def healthz():
        g.db.execute(text('SELECT 1'))
        return jsonify(status='ok', service='lise-api')

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error=error.description or 'Solicitação inválida.'), error.code or 400

    @app.errorhandler(Exception)
    def unexpected_error(error):
        if app.testing:
            raise error
        if hasattr(g, 'db'):
            g.db.rollback()
        app.logger.error('Falha na API LISE: %s', type(error).__name__)
        return jsonify(error='Ocorreu um erro. Tente novamente em instantes.'), 503

    app.register_blueprint(api)
    return app


if __name__ == '__main__':
    create_app().run(host='127.0.0.1', port=int(os.getenv('PORT', '5000')), debug=False)
