from app.repository.exclusions import RepositoryExclusions


def test_default_directories_are_excluded():
    exclusions = RepositoryExclusions()
    assert exclusions.is_excluded("project/node_modules/file.js")
    assert exclusions.is_excluded("project/.git/config")
    assert exclusions.is_excluded("project/.venv/pyvenv.cfg")


def test_sensitive_files_are_excluded_but_config_files_remain():
    exclusions = RepositoryExclusions()
    assert exclusions.is_sensitive(".env")
    assert exclusions.is_sensitive("private.pem")
    assert not exclusions.is_excluded("config/appsettings.json")
    assert not exclusions.is_excluded("deployment.yaml")


def test_custom_exclusions_are_supported():
    exclusions = RepositoryExclusions(extra_patterns=("*.generated.cs",), extra_directories={"cache"})
    assert exclusions.is_excluded("file.generated.cs")
    assert exclusions.is_excluded("cache/data.txt")
