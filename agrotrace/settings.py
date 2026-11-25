"""
Configuración de AgroTrace-UPEC – Procedencia digital de productos hortofrutícolas.

Los valores sensibles se leen de variables de entorno o del archivo `.env`
(copie `.env.example` como `.env` y ajústelo). Base de datos por defecto: SQLite.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _cargar_env(ruta):
    """Lector mínimo de archivos .env (CLAVE=valor), sin dependencias externas."""
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#") and "=" in linea:
            clave, valor = linea.split("=", 1)
            os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


_cargar_env(BASE_DIR / ".env")


def env(clave, defecto=""):
    return os.environ.get(clave, defecto)


SECRET_KEY = env("DJANGO_SECRET_KEY", "solo-para-desarrollo-cambie-esta-clave")
DEBUG = env("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = [h.strip() for h in env("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost,*").split(",")]
CSRF_TRUSTED_ORIGINS = [o for o in env("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "rest_framework",
    "rest_framework.authtoken",
    # Aplicaciones del proyecto
    "cuentas",
    "dashboard",
    "productores",
    "parcelas",
    "productos",
    "cosechas",
    "lotes",
    "trazabilidad",
    "transporte",
    "reportes",
    "comercial",
    "api",
    "asistente",
    "integracion",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "cuentas.middleware.UsuarioActualMiddleware",
]

ROOT_URLCONF = "agrotrace.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "cuentas.context_processors.menu",
            ],
        },
    },
]

WSGI_APPLICATION = "agrotrace.wsgi.application"

# ---- Base de datos: sqlite (desarrollo), postgres o mysql ----
_motor = env("DB_ENGINE", "sqlite")
if _motor == "postgres":
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME", "agrotrace"), "USER": env("DB_USER", "postgres"),
        "PASSWORD": env("DB_PASSWORD"), "HOST": env("DB_HOST", "127.0.0.1"), "PORT": env("DB_PORT", "5432"),
    }}
elif _motor == "mysql":
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": env("DB_NAME", "agrotrace"), "USER": env("DB_USER", "root"),
        "PASSWORD": env("DB_PASSWORD"), "HOST": env("DB_HOST", "127.0.0.1"), "PORT": env("DB_PORT", "3306"),
        "OPTIONS": {"charset": "utf8mb4"},
    }}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

LANGUAGE_CODE = "es-ec"
TIME_ZONE = "America/Guayaquil"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "inicio"
LOGOUT_REDIRECT_URL = "login"

# Sesión y cookies
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = 60 * 60 * 8          # 8 horas
CSRF_COOKIE_HTTPONLY = False
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
if not DEBUG:
    # Publicado en internet (por ejemplo, PythonAnywhere con https)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer", "rest_framework.renderers.BrowsableAPIRenderer"],
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.UserRateThrottle", "rest_framework.throttling.AnonRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"user": "600/min", "anon": "30/min"},
}

# ---- Identificación GS1 ----
SITE_URL = env("SITE_URL", "http://127.0.0.1:8000")
GS1_PREFIJO_EMPRESA = env("GS1_PREFIJO_EMPRESA", "7861234")

# ---- Integraciones (F5) ----
N8N_WEBHOOK_COSECHA = env("N8N_WEBHOOK_COSECHA", "")
ODOO_URL = env("ODOO_URL", "http://localhost:8069")
ODOO_DB = env("ODOO_DB", "upec")
ODOO_USER = env("ODOO_USER", "admin")
ODOO_PASSWORD = env("ODOO_PASSWORD", "admin")

PAGINACION = 15

# ---- Asistente virtual con IA (opcional) ----
# ninguno: solo reglas con consultas a la base de datos (funciona sin internet)
# anthropic: API de Claude · openai: cualquier API compatible con OpenAI (Ollama local, LM Studio, Groq, OpenAI)
IA_PROVEEDOR = env("IA_PROVEEDOR", "ninguno")
IA_URL = env("IA_URL", "")
IA_MODELO = env("IA_MODELO", "")
IA_API_KEY = env("IA_API_KEY", "")
IA_TIEMPO = int(env("IA_TIEMPO", "20"))
