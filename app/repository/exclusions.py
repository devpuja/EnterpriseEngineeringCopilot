from fnmatch import fnmatch
from pathlib import Path


DEFAULT_EXCLUDED_DIRECTORIES = {
    ".git", ".venv", "venv", "env", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "node_modules", "dist", "build",
    "coverage", ".next", ".angular", "bin", "obj", "target", "vendor",
}

DEFAULT_EXCLUDED_PATTERNS = (
    "*.env", ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx",
    "id_rsa", "id_ed25519", "*.pyc", "*.pyo", "*.class", "*.jar",
    "*.dll", "*.exe", "*.so", "*.dylib", "*.zip", "*.tar", "*.gz",
    ".DS_Store", "Thumbs.db",
)


class RepositoryExclusions:
    def __init__(self, extra_patterns: tuple[str, ...] = (), extra_directories: set[str] | None = None):
        self.patterns = (*DEFAULT_EXCLUDED_PATTERNS, *extra_patterns)
        self.directories = DEFAULT_EXCLUDED_DIRECTORIES | (extra_directories or set())

    def is_sensitive(self, relative_path: str) -> bool:
        name = Path(relative_path).name
        return name == ".env" or any(fnmatch(name, pattern) for pattern in self.patterns)

    def is_excluded_directory(self, name: str) -> bool:
        normalized_name = name.lower().lstrip("./")
        return any(
            normalized_name == item.lower().lstrip("./")
            for item in self.directories
        )

    def is_excluded(self, relative_path: str) -> bool:
        path = Path(relative_path)
        if any(self.is_excluded_directory(part) for part in path.parts):
            return True
        return any(fnmatch(path.name, pattern) for pattern in self.patterns)
