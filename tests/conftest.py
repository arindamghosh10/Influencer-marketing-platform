import pytest
from django.core.management import call_command

from apps.accounts.models import User
from apps.brands.models import BrandProfile


@pytest.fixture(autouse=True)
def _settings(settings):
    settings.LLM_PROVIDER = "rules"
    settings.INSTAGRAM_PROVIDER = "mock"
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


@pytest.fixture
def seeded(db):
    call_command("seed_demo", creators=60, verbosity=0)


@pytest.fixture
def brand_user(db):
    user = User.objects.create_user("brand@test.local", "pw-Strong-123", role=User.Role.BRAND)
    BrandProfile.objects.create(
        user=user,
        company_name="TestCo",
        gstin="27AAPFU0939F1ZV",
        pan="AAPFU0939F",
        status=BrandProfile.Status.APPROVED,
    )
    return user


@pytest.fixture
def creator_user(db):
    return User.objects.create_user(
        "creator@test.local", "pw-Strong-123", role=User.Role.CREATOR, first_name="Asha", last_name="Rao"
    )


@pytest.fixture(autouse=True)
def _fast_passwords(settings):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
