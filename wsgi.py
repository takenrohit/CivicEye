"""Entry point: `flask --app wsgi run` (loads .env automatically if python-dotenv is installed)."""
from dotenv import load_dotenv

load_dotenv()

from civiceye import create_app  # noqa: E402

app = create_app()
