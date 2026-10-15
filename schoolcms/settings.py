import os
from pathlib import Path
import dj_database_url
from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

def env_value(name, default=None):
    value, filename = os.getenv(name), os.getenv(name + "_FILE")
    if value is not None and filename:
        raise ImproperlyConfigured(f"Set only {name} or {name}_FILE, not both.")
    if filename:
        try:
            return Path(filename).read_text().strip()
        except OSError as exc:
            raise ImproperlyConfigured(f"Cannot read {name}_FILE.") from exc
    return value if value is not None else default


def env_bool(name, default=False):
    value = str(env_value(name, str(default))).lower()
    if value not in {"true", "false", "1", "0"}:
        raise ImproperlyConfigured(f"{name} must be true or false.")
    return value in {"true", "1"}


DEBUG = env_bool("DJANGO_DEBUG")
SECRET_KEY = env_value("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "dev-only-schoolcms-key-rotate-before-deployment-7abf31d0"  # nosec B105  # DEBUG-only; production rejects this value.
    else:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is false.")
if not DEBUG and (any(marker in SECRET_KEY.lower() for marker in ("change-me", "development", "dev-only", "replace-in-")) or len(SECRET_KEY) < 50 or len(set(SECRET_KEY)) < 12):
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be a strong, non-placeholder key in production.")
ALLOWED_HOSTS = [h.strip() for h in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [v.strip() for v in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if v.strip()]
if not DEBUG and (not os.getenv("DJANGO_ALLOWED_HOSTS") or not ALLOWED_HOSTS or any("*" in h for h in ALLOWED_HOSTS)):
    raise ImproperlyConfigured("Production requires explicit DJANGO_ALLOWED_HOSTS without wildcards.")
if not DEBUG and (not CSRF_TRUSTED_ORIGINS or any(not v.startswith("https://") or "*" in v for v in CSRF_TRUSTED_ORIGINS)):
    raise ImproperlyConfigured("Production requires explicit HTTPS DJANGO_CSRF_TRUSTED_ORIGINS.")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "schools",
    "academics",
    "students",
    "learning",
    "assessment",
    "finance",
    "oversight",
    "privatefiles.apps.PrivateFilesConfig",
    "audit.apps.AuditConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "accounts.middleware.ActiveUserMiddleware",
    "accounts.middleware.MFARequiredMiddleware",
    "schoolcms.middleware.PrivateResponseMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "schoolcms.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "schoolcms.wsgi.application"
ASGI_APPLICATION = "schoolcms.asgi.application"

database_url = env_value("DATABASE_URL")
if not DEBUG and not database_url:
    raise ImproperlyConfigured("Production requires a PostgreSQL DATABASE_URL.")
DATABASES = {"default": dj_database_url.parse(database_url or f"sqlite:///{BASE_DIR / 'db.sqlite3'}", conn_max_age=60, conn_health_checks=True)}
if not DEBUG and DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":
    raise ImproperlyConfigured("Production requires PostgreSQL; SQLite is development-only.")

AUTHENTICATION_BACKENDS = ["accounts.auth_backends.ThrottleBackend"]
MFA_ENCRYPTION_KEY = env_value("MFA_ENCRYPTION_KEY", "")
MFA_REQUIRED_FOR_STAFF = not DEBUG
MFA_REQUIRED_FOR_PRIVILEGED_ROLES = not DEBUG
if not DEBUG:
    from cryptography.fernet import Fernet
    try:
        Fernet(MFA_ENCRYPTION_KEY.encode())
    except (ValueError, TypeError) as exc:
        raise ImproperlyConfigured("Production requires a separate valid MFA_ENCRYPTION_KEY.") from exc

AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "logged_out"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Karachi"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
WHITENOISE_AUTOREFRESH = DEBUG
WHITENOISE_USE_FINDERS = DEBUG
PRIVATE_FILE_ROOT = Path(env_value("PRIVATE_FILE_ROOT", str(BASE_DIR / "privatefiles_data"))).resolve()
PRIVATE_FILE_MAX_BYTES = 10 * 1024 * 1024
PRIVATE_FILE_SCAN_TIMEOUT = 30
PRIVATE_FILE_SCANNER_COMMAND = env_value("PRIVATE_FILE_SCANNER_COMMAND", "")
if not DEBUG:
    if not env_value("PRIVATE_FILE_ROOT") or not Path(env_value("PRIVATE_FILE_ROOT")).is_absolute() or PRIVATE_FILE_ROOT.is_relative_to(BASE_DIR):
        raise ImproperlyConfigured("Production requires an absolute persistent PRIVATE_FILE_ROOT outside the application directory.")
    if not PRIVATE_FILE_SCANNER_COMMAND:
        raise ImproperlyConfigured("Production requires a fail-closed PRIVATE_FILE_SCANNER_COMMAND.")
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = PRIVATE_FILE_MAX_BYTES + 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000
DATA_UPLOAD_MAX_NUMBER_FILES = 5
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
EMAIL_BACKEND = os.getenv(
    "DJANGO_EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend" if DEBUG else "django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = os.getenv("DJANGO_EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.getenv("DJANGO_EMAIL_PORT", "25"))
EMAIL_HOST_USER = os.getenv("DJANGO_EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env_value("DJANGO_EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("DJANGO_EMAIL_USE_TLS", "false").lower() == "true"
EMAIL_USE_SSL = os.getenv("DJANGO_EMAIL_USE_SSL", "false").lower() == "true"
DEFAULT_FROM_EMAIL = os.getenv("DJANGO_DEFAULT_FROM_EMAIL", "School-CMS <no-reply@example.com>")
EMAIL_TIMEOUT = 10
SERVER_EMAIL = DEFAULT_FROM_EMAIL
if not DEBUG:
    if EMAIL_BACKEND != "django.core.mail.backends.smtp.EmailBackend" or not os.getenv("DJANGO_EMAIL_HOST") or EMAIL_HOST in {"localhost", "127.0.0.1"}:
        raise ImproperlyConfigured("Production requires an explicit SMTP delivery host/backend.")
    if EMAIL_USE_TLS == EMAIL_USE_SSL:
        raise ImproperlyConfigured("Production requires exactly one of SMTP TLS or SSL.")
    if not os.getenv("DJANGO_DEFAULT_FROM_EMAIL"):
        raise ImproperlyConfigured("Production requires DJANGO_DEFAULT_FROM_EMAIL.")

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 3600
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
SECURE_REDIRECT_EXEMPT = [r"^health/live/$", r"^health/ready/$"]
# Enable only when the application port is isolated and the edge strips and
# overwrites forwarded headers. Never trust a header on an Internet-facing port.
TRUST_PROXY_HEADERS = env_bool("DJANGO_TRUST_PROXY")
if TRUST_PROXY_HEADERS:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
    # Enable HSTS only after confirming every deployment subdomain supports HTTPS.
    SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_HSTS_SECONDS", "3600"))
    if SECURE_HSTS_SECONDS < 3600:
        raise ImproperlyConfigured("Production HSTS must be at least 3600 seconds.")
    SECURE_HSTS_INCLUDE_SUBDOMAINS = os.getenv("DJANGO_HSTS_INCLUDE_SUBDOMAINS", "false").lower() == "true"
    SECURE_HSTS_PRELOAD = os.getenv("DJANGO_HSTS_PRELOAD", "false").lower() == "true"
