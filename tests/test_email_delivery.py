from backend.config import Settings
from backend.services.email_delivery import build_account_action_url


def test_account_action_url_keeps_secret_in_fragment() -> None:
    settings = Settings(
        _env_file=None,
        FRONTEND_PUBLIC_URL="https://evalflow.example/app/",
    )

    url = build_account_action_url(
        settings,
        "reset-password",
        "secret-token_value",
    )

    assert url == (
        "https://evalflow.example/app/#action=reset-password&"
        "token=secret-token_value"
    )
    assert "secret-token_value" not in url.split("#", maxsplit=1)[0]
