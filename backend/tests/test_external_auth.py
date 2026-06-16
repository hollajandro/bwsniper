from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, User, UserConfig
from app.services.auth_service import get_or_create_external_user, hash_password


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    return Session()


def test_external_auth_links_existing_user_by_email():
    db = make_session()
    user = User(
        email="admin@example.com",
        password_hash=hash_password("existing-password"),
        display_name="Admin",
        is_admin=True,
    )
    db.add(user)
    db.add(UserConfig(user=user, config_json="{}"))
    db.commit()

    resolved = get_or_create_external_user(
        db,
        provider="cloudflare_access",
        subject="authentik-user-1",
        email="ADMIN@example.com",
        display_name="Admin User",
        auto_create=False,
    )

    assert resolved.id == user.id
    assert resolved.is_admin is True
    assert resolved.auth_provider == "cloudflare_access"
    assert resolved.external_subject == "authentik-user-1"


def test_external_auth_auto_creates_user_when_enabled():
    db = make_session()

    user = get_or_create_external_user(
        db,
        provider="cloudflare_access",
        subject="authentik-user-2",
        email="new@example.com",
        display_name="New User",
        auto_create=True,
        admin_emails={"new@example.com"},
    )

    assert user.email == "new@example.com"
    assert user.display_name == "New User"
    assert user.is_admin is True
    assert db.query(UserConfig).filter(UserConfig.user_id == user.id).first()


def test_external_auth_respects_auto_create_disabled():
    db = make_session()

    try:
        get_or_create_external_user(
            db,
            provider="cloudflare_access",
            subject="authentik-user-3",
            email="missing@example.com",
            auto_create=False,
        )
    except ValueError as ex:
        assert "No BwSniper user exists" in str(ex)
    else:
        raise AssertionError("Expected missing external user to be rejected")
