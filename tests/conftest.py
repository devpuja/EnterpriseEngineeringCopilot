import pytest


@pytest.fixture(autouse=True)
def authenticated_main_app_for_existing_api_tests():
    from main import app
    from app.security import Role, UserPrincipal, get_current_principal

    previous = app.dependency_overrides.get(get_current_principal)
    app.dependency_overrides[get_current_principal] = lambda: UserPrincipal(
        subject="test-user",
        issuer="https://test-issuer.example",
        roles=frozenset(Role),
    )
    yield
    if previous is None:
        app.dependency_overrides.pop(get_current_principal, None)
    else:
        app.dependency_overrides[get_current_principal] = previous