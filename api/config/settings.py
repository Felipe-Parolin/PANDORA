import os
import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-only-pandora-change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"
ALLOWED_HOSTS = [x.strip() for x in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",") if x.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt",
    "accounts",
    "core",
    "customers",
    "assets",
    "maintenance",
    "rentals",
    "logistics",
    "commercial",
    "ai",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"

if os.getenv("DB_ENGINE", "postgresql") == "postgresql":
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME", "pandora_db"),
        "USER": os.getenv("DB_USER", "pandora_app"),
        "PASSWORD": os.getenv("DB_PASSWORD", ""),
        "HOST": os.getenv("DB_HOST", "localhost"),
        "PORT": os.getenv("DB_PORT", "5432"),
        "CONN_MAX_AGE": int(os.getenv("DB_CONN_MAX_AGE", "60")),
        "OPTIONS": {"sslmode": os.getenv("DB_SSLMODE", "prefer")},
    }}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CORS_ALLOWED_ORIGINS = [x.strip() for x in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if x.strip()]
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://127.0.0.1:5173")
BACKEND_PUBLIC_URL = os.getenv("BACKEND_PUBLIC_URL", "http://127.0.0.1:8000")
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "true").lower() == "true"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "")
GEOCODING_ENABLED = os.getenv("GEOCODING_ENABLED", "true").lower() == "true"
GEOCODING_SEARCH_URL = os.getenv("GEOCODING_SEARCH_URL", "https://nominatim.openstreetmap.org/search").strip()
FREIGHT_ORIGIN_CEP = os.getenv("FREIGHT_ORIGIN_CEP", "").strip() or "13614032"
_default_freight_address = "Av. Joaquim Lopes Aguila, 3000 - Barra Funda, Leme - SP, 13614-032"
FREIGHT_ORIGIN_ADDRESS = os.getenv("FREIGHT_ORIGIN_ADDRESS", "").strip() or _default_freight_address
FREIGHT_ORIGIN_LABEL = os.getenv("FREIGHT_ORIGIN_LABEL", "").strip() or FREIGHT_ORIGIN_ADDRESS
_default_freight_point = FREIGHT_ORIGIN_ADDRESS == _default_freight_address
# Ponto do estabelecimento no link fornecido por Felipe; não é o centro da avenida.
FREIGHT_ORIGIN_LATITUDE = os.getenv("FREIGHT_ORIGIN_LATITUDE", "").strip() or ("-22.1757125" if _default_freight_point else "")
FREIGHT_ORIGIN_LONGITUDE = os.getenv("FREIGHT_ORIGIN_LONGITUDE", "").strip() or ("-47.3820152" if _default_freight_point else "")
FREIGHT_ORIGIN_PROVISIONAL = False
# O servidor público é somente para desenvolvimento. Em produção, configure um serviço próprio/contratado.
FREIGHT_ROUTING_URL = os.getenv("FREIGHT_ROUTING_URL", "https://router.project-osrm.org" if DEBUG else "").strip()
FREIGHT_MINIMUM_PER_LEG = Decimal(os.getenv("FREIGHT_MINIMUM_PER_LEG", "25.00"))
FREIGHT_RATE_PER_KM = Decimal(os.getenv("FREIGHT_RATE_PER_KM", "3.00"))
FREIGHT_ROAD_FACTOR = Decimal(os.getenv("FREIGHT_ROAD_FACTOR", "1.30"))
# Assistente de IA (Groq). A chave deve ser configurada apenas no .env local.
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
AI_ENABLED = os.getenv("AI_ENABLED", "true").lower() == "true"
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
AI_MODEL = os.getenv("AI_MODEL", "llama-3.3-70b-versatile")
AI_TRANSCRIPTION_MODEL = os.getenv("AI_TRANSCRIPTION_MODEL", "whisper-large-v3-turbo")
AI_TIMEOUT_SECONDS = float(os.getenv("AI_TIMEOUT_SECONDS", "30"))
AI_RESULT_LIMIT = int(os.getenv("AI_RESULT_LIMIT", "5"))
AI_MAX_CONTEXT_CHARS = int(os.getenv("AI_MAX_CONTEXT_CHARS", "12000"))
AI_MAX_AUDIO_BYTES = int(os.getenv("AI_MAX_AUDIO_BYTES", str(10 * 1024 * 1024)))
AI_RATE_LIMIT = os.getenv("AI_RATE_LIMIT", "40/min")
AI_BREAKER_FAILURES = int(os.getenv("AI_BREAKER_FAILURES", "3"))
AI_BREAKER_COOLDOWN_SECONDS = int(os.getenv("AI_BREAKER_COOLDOWN_SECONDS", "60"))

FREIGHT_ITEMS_PER_TRIP = int(os.getenv("FREIGHT_ITEMS_PER_TRIP", "3"))
FREIGHT_OPERATIONAL_COST_PER_TRIP = Decimal(os.getenv("FREIGHT_OPERATIONAL_COST_PER_TRIP", "0.00"))
FREIGHT_EXTRA_FEE = Decimal(os.getenv("FREIGHT_EXTRA_FEE", "0.00"))
try:
    FREIGHT_CITY_SURCHARGES = json.loads(os.getenv("FREIGHT_CITY_SURCHARGES", "{}"))
except (TypeError, ValueError):
    FREIGHT_CITY_SURCHARGES = {}
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ("rest_framework_simplejwt.authentication.JWTAuthentication",),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer", "rest_framework.renderers.BrowsableAPIRenderer"),
    "EXCEPTION_HANDLER": "core.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_RATES": {"ai": AI_RATE_LIMIT},
}
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=8),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "AUTH_HEADER_TYPES": ("Bearer",),
}
