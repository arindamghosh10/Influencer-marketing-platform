"""Django settings. All environment-specific values come from environment variables (see .env.example)."""

from pathlib import Path

import environ
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env", overwrite=False)

SECRET_KEY = env("SECRET_KEY", default="dev-insecure-change-me")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django_htmx",
    "django_tailwind_cli",
    "apps.core",
    "apps.accounts",
    "apps.niches",
    "apps.brands",
    "apps.creators",
    "apps.campaigns",
    "apps.matching",
    "apps.contracts",
    "apps.integrations",
    "apps.offers",
    "apps.payments",
    "apps.content",
    "apps.reports",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
]

ROOT_URLCONF = "config.urls"

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
                "apps.core.context_processors.platform",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": env.db("DATABASE_URL", default="postgres://app:app@localhost:5432/influencer"),
}
DATABASES["default"]["ATOMIC_REQUESTS"] = True

AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:home"
LOGOUT_REDIRECT_URL = "core:landing"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-in"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = env.path("MEDIA_ROOT", default=BASE_DIR / "media")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Tailwind (standalone CLI, no Node.js needed)
TAILWIND_CLI_SRC_CSS = "assets/tailwind/source.css"
TAILWIND_CLI_DIST_CSS = "css/tailwind.css"

# Celery
CELERY_BROKER_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)
CELERY_TIMEZONE = TIME_ZONE

# Email (v1: console in dev, Brevo/Gmail SMTP in prod via EMAIL_URL)
EMAIL_CONFIG = env.email_url("EMAIL_URL", default="consolemail://")
vars().update(EMAIL_CONFIG)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@localhost")

# Security hardening when not in DEBUG
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=0)
    SECURE_CONTENT_TYPE_NOSNIFF = True

# ---------------------------------------------------------------------------
# Platform business settings
# ---------------------------------------------------------------------------
PLATFORM_NAME = env("PLATFORM_NAME", default="CreatorBridge")
# Share of the brand price the platform keeps, in basis points (5000 = 50%).
# Never shown to brands or creators.
PLATFORM_MARGIN_BPS = env.int("PLATFORM_MARGIN_BPS", default=5000)
GST_RATE_BPS = env.int("GST_RATE_BPS", default=1800)
# TDS on creator payouts; confirm section and rate with your CA.
TDS_RATE_BPS_INDIVIDUAL = env.int("TDS_RATE_BPS_INDIVIDUAL", default=100)
TDS_RATE_BPS_COMPANY = env.int("TDS_RATE_BPS_COMPANY", default=200)
OFFER_EXPIRY_HOURS = env.int("OFFER_EXPIRY_HOURS", default=48)
BRAND_REVIEW_HOURS = env.int("BRAND_REVIEW_HOURS", default=72)
VERIFICATION_DAYS = env.int("VERIFICATION_DAYS", default=7)
MIN_LIVE_DAYS = env.int("MIN_LIVE_DAYS", default=30)
MIN_AUTHENTICITY_SCORE = env.int("MIN_AUTHENTICITY_SCORE", default=60)

# ---------------------------------------------------------------------------
# Integration adapters: pick an implementation per service.
# ---------------------------------------------------------------------------
LLM_PROVIDER = env("LLM_PROVIDER", default="rules")  # "gemini" | "rules"
GEMINI_API_KEY = env("GEMINI_API_KEY", default="")
GEMINI_MODEL = env("GEMINI_MODEL", default="gemini-2.5-flash")
INSTAGRAM_PROVIDER = env("INSTAGRAM_PROVIDER", default="mock")  # "mock" | "graph"
PAYMENTS_PROVIDER = env("PAYMENTS_PROVIDER", default="mock")  # "mock" | "razorpay"
# Allow product-page fetches to private IPs (tests/dev only; never in production).
FETCH_ALLOW_PRIVATE_HOSTS = env.bool("FETCH_ALLOW_PRIVATE_HOSTS", default=False)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
}

# Keys for EncryptedTextField (PAN, bank details). Generate with:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
FIELD_ENCRYPTION_KEYS = env.list("FIELD_ENCRYPTION_KEYS", default=[])

# Instagram (Meta app credentials, used when INSTAGRAM_PROVIDER=graph)
INSTAGRAM_APP_ID = env("INSTAGRAM_APP_ID", default="")
INSTAGRAM_APP_SECRET = env("INSTAGRAM_APP_SECRET", default="")

# Offers and payments
# Hours a brand has to pay after a creator accepts, before the slot is released.
BRAND_PAYMENT_HOURS = env.int("BRAND_PAYMENT_HOURS", default=120)
RAZORPAY_KEY_ID = env("RAZORPAY_KEY_ID", default="")
RAZORPAY_KEY_SECRET = env("RAZORPAY_KEY_SECRET", default="")
RAZORPAY_WEBHOOK_SECRET = env("RAZORPAY_WEBHOOK_SECRET", default="")

# Seller details printed on GST invoices
PLATFORM_LEGAL_NAME = env("PLATFORM_LEGAL_NAME", default="CreatorBridge Private Limited")
PLATFORM_GSTIN = env("PLATFORM_GSTIN", default="")
PLATFORM_ADDRESS = env("PLATFORM_ADDRESS", default="")
# GST state code of the platform's registration; decides CGST+SGST vs IGST.
PLATFORM_STATE_CODE = env("PLATFORM_STATE_CODE", default="27")
SAC_CODE = env("SAC_CODE", default="998361")  # Advertising services
INVOICE_PREFIX = env("INVOICE_PREFIX", default="CB")

# Scheduled jobs (Celery Beat). Deadlines live in the database, so a missed run just
# gets picked up by the next one.
CELERY_BEAT_SCHEDULE = {
    "process-deadlines": {
        "task": "apps.offers.tasks.process_deadlines",
        "schedule": 300.0,
    },
    "weekly-brand-reports": {
        "task": "apps.reports.tasks.weekly_reports",
        "schedule": crontab(hour=9, minute=0, day_of_week="mon"),  # CELERY_TIMEZONE is Asia/Kolkata
    },
}

# Content
SITE_URL = env("SITE_URL", default="http://localhost:8000")  # used for public media links for Instagram
MAX_REVISIONS = env.int("MAX_REVISIONS", default=2)
MAX_UPLOAD_MB = env.int("MAX_UPLOAD_MB", default=250)
