"""Django settings for the IELTS backend migration scaffold."""

import os

from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


def env_flag(name: str, default: bool = False) -> bool:
    value = str(os.environ.get(name, "1" if default else "0")).strip().lower()
    return value in {"1", "true", "yes", "on"}


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "django-insecure-local-ielts-migration-only")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"

ALLOWED_HOSTS = [host for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",") if host]


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    "rest_framework",
    "apps.common",
    "apps.accounts",
    "apps.ai",
    "apps.billing",
    "apps.speaking",
    "apps.writing",
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    'default': {
        "ENGINE": os.environ.get("DJANGO_DB_ENGINE", "django.db.backends.sqlite3"),
        "NAME": os.environ.get("DJANGO_DB_NAME", str(BASE_DIR / "db.sqlite3")),
        "USER": os.environ.get("DJANGO_DB_USER", ""),
        "PASSWORD": os.environ.get("DJANGO_DB_PASSWORD", ""),
        "HOST": os.environ.get("DJANGO_DB_HOST", ""),
        "PORT": os.environ.get("DJANGO_DB_PORT", ""),
    }
}


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = 'static/'

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = "accounts.CustomUser"

PROJECT_OWNER_NAME = os.environ.get("PROJECT_OWNER_NAME", "TBD")
PROJECT_OWNER_EMAIL = os.environ.get("PROJECT_OWNER_EMAIL", "TBD")
PROJECT_VERSION = os.environ.get("PROJECT_VERSION", "django-migration-m1")

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
    ],
}

AI_PROVIDER_MODE = str(os.environ.get("AI_PROVIDER_MODE", "local_safe")).strip().lower() or "local_safe"
AI_DEFAULT_PROVIDER = str(os.environ.get("AI_DEFAULT_PROVIDER", "codex")).strip().lower() or "codex"
AI_ALLOW_MOCK_SUCCESS = env_flag("AI_ALLOW_MOCK_SUCCESS", default=False)
AI_PROVIDER_ENABLE_CODEX = env_flag("AI_PROVIDER_ENABLE_CODEX", default=True)
AI_PROVIDER_ENABLE_OPENAI = env_flag("AI_PROVIDER_ENABLE_OPENAI", default=False)
AI_PROVIDER_ENABLE_CLAUDE = env_flag("AI_PROVIDER_ENABLE_CLAUDE", default=False)
# Placeholder env-var names for future integrations. Keep only the names here,
# never the secret values.
AI_PROVIDER_SECRET_ENV_NAMES = {
    "codex": ("CODEX_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
    "claude": ("ANTHROPIC_API_KEY",),
    "mock_success": (),
    "fallback": (),
}
