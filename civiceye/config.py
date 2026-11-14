"""Configuration. All secrets come from environment variables (see .env.example)."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


class Config:
    SECRET_KEY = os.environ.get("CIVICEYE_SECRET_KEY")  # validated in create_app

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "CIVICEYE_DATABASE_URL", f"sqlite:///{(BASE_DIR / 'instance' / 'civiceye.db').as_posix()}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # File storage (outside static/, served only through authorised routes)
    UPLOAD_DIR = os.environ.get("CIVICEYE_UPLOAD_DIR", str(BASE_DIR / "instance" / "uploads"))
    MAX_CONTENT_LENGTH = _int("CIVICEYE_MAX_REQUEST_MB", 40) * 1024 * 1024
    MAX_IMAGE_BYTES = _int("CIVICEYE_MAX_IMAGE_MB", 8) * 1024 * 1024
    MAX_IMAGE_PIXELS = 40_000_000
    MIN_IMAGE_SIDE = 64
    MAX_IMAGE_SIDE = 10_000
    MAX_EXTRA_IMAGES = _int("CIVICEYE_MAX_EXTRA_IMAGES", 3)

    DESCRIPTION_MIN = 10
    DESCRIPTION_MAX = 1000
    LANDMARK_MAX = 120

    # Session / cookies. Set CIVICEYE_SECURE_COOKIES=1 when served over HTTPS.
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool("CIVICEYE_SECURE_COOKIES", False)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 8

    WTF_CSRF_TIME_LIMIT = 60 * 60 * 4

    RATELIMIT_ENABLED = _bool("CIVICEYE_RATELIMIT_ENABLED", True)
    RATELIMIT_STORAGE_URI = os.environ.get("CIVICEYE_RATELIMIT_STORAGE", "memory://")
    LOGIN_RATE_LIMIT = "10 per minute"
    REGISTER_RATE_LIMIT = "5 per minute"
    SUBMIT_RATE_LIMIT = "10 per hour"

    DISPLAY_TZ = "Asia/Kolkata"

    # Map. OpenStreetMap's public tiles have a usage policy; review it before any
    # public deployment and switch providers via env if needed.
    MAP_TILE_URL = os.environ.get("CIVICEYE_MAP_TILE_URL", "https://tile.openstreetmap.org/{z}/{x}/{y}.png")
    MAP_TILE_ATTRIBUTION = os.environ.get(
        "CIVICEYE_MAP_ATTRIBUTION",
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    )
    # Approximate centre near DSCE, Kumaraswamy Layout. Verify manually.
    MAP_DEFAULT_CENTER = (12.9081, 77.5665)
    MAP_DEFAULT_ZOOM = 16

    # Nearby / potential duplicate check (conservative pilot defaults)
    DUPLICATE_RADIUS_M = _int("CIVICEYE_DUPLICATE_RADIUS_M", 30)
    DUPLICATE_WINDOW_DAYS = _int("CIVICEYE_DUPLICATE_WINDOW_DAYS", 30)

    # Priority engine: P = 0.45R + 0.25L + 0.20A + 0.10C (weights are a design
    # choice, not scientifically validated)
    PRIORITY_WEIGHTS = {"R": 0.45, "L": 0.25, "A": 0.20, "C": 0.10}
    PRIORITY_AGE_CAP_DAYS = _int("CIVICEYE_PRIORITY_AGE_CAP_DAYS", 30)
    PRIORITY_CORROBORATION_CAP = _int("CIVICEYE_PRIORITY_CORROBORATION_CAP", 4)
    PRIORITY_BANDS = [(0.70, "High"), (0.40, "Medium"), (0.0, "Low")]

    # Optional image model weights. Empty = image AI unavailable (honest state).
    IMAGE_MODEL_WEIGHTS = os.environ.get("CIVICEYE_IMAGE_WEIGHTS", "")

    # Optional outbound channels: disabled unless configured (not implemented in phase 1)
    EMAIL_ENABLED = False
    SMS_ENABLED = False


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "test-only-secret-key"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
