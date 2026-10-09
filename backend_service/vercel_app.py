"""Vercel entrypoint for the LISE Flask API."""
from app import create_app

app = create_app()
