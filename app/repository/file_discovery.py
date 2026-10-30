import hashlib
import logging
import os
from pathlib import Path

from app.config.settings import settings
from app.repository.exceptions import RepositoryLimitExceededError, RepositorySecurityError
from app.repository.exclusions import RepositoryExclusions
from app.repository.models import RepositoryFile


logger = logging.getLogger(__name__)

LANGUAGE_EXTENSIONS = {
    ".cs": "C#",
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript/React",
    ".jsx": "JavaScript/React",
    ".html": "HTML",
}


def is_binary_file(path: Path, sample_size: int = 8192) -> bool:
    try:
        with path.open("rb") as handle:
            sample = handle.read(sample_size)
        if b"\x00" in sample:
            return True
        if not sample:
            return False
        text_chars = sum(byte in b"\n\r\t\b\f" or 32 <= byte <= 126 for byte in sample)
        return text_chars / len(sample) < 0.30
    except OSError:
        return False


class FileDiscovery:
    def __init__(
        self,
        exclusions: RepositoryExclusions | None = None,
        maximum_file_size: int | None = None,
        maximum_file_count: int | None = None,
        maximum_repository_size: int | None = None,
        maximum_depth: int | None = None,
    ):
        self.exclusions = exclusions or RepositoryExclusions()
        self.maximum_file_size = maximum_file_size or settings.maximum_repository_file_size_bytes
        self.maximum_file_count = maximum_file_count or settings.maximum_repository_file_count
        self.maximum_repository_size = maximum_repository_size or settings.maximum_repository_size_bytes
        self.maximum_depth = maximum_depth if maximum_depth is not None else settings.maximum_directory_traversal_depth

    def _technology_names(self, relative: Path) -> list[str]:
        name = relative.name.lower()
        suffix = relative.suffix.lower()
        technologies: list[str] = []
        if suffix == ".cs" or suffix in {".csproj", ".sln"}:
            technologies.append(".NET/C#")
        if suffix == ".py" or name in {"pyproject.toml", "requirements.txt"}:
            technologies.append("Python")
        if name == "angular.json" or suffix in {".ts", ".html"}:
            technologies.append("Angular")
        if suffix in {".jsx", ".tsx"} or name == "package.json":
            technologies.append("React")
        return list(dict.fromkeys(technologies))

    def discover(self, repository_root: str | Path) -> list[RepositoryFile]:
        root = Path(repository_root).resolve(strict=True)
        discovered: list[RepositoryFile] = []
        total_size = 0

        for current_root, directories, filenames in os.walk(root, topdown=True, followlinks=False):
            current = Path(current_root)
            relative_current = current.relative_to(root)
            depth = 0 if str(relative_current) == "." else len(relative_current.parts)
            if depth > self.maximum_depth:
                directories[:] = []
                continue

            directories[:] = [
                directory for directory in directories
                if not self.exclusions.is_excluded_directory(directory)
                and not (current / directory).is_symlink()
            ]

            for filename in filenames:
                path = current / filename
                try:
                    relative = path.relative_to(root)
                except ValueError:
                    continue
                if self.exclusions.is_excluded(relative.as_posix()):
                    continue
                try:
                    if path.is_symlink():
                        raise RepositorySecurityError("Symlink traversal is not allowed during file discovery.")
                    stat = path.stat()
                    if not path.is_file():
                        continue
                    if stat.st_size > self.maximum_file_size:
                        raise RepositoryLimitExceededError(
                            f"File exceeds maximum allowed size: {relative.as_posix()}"
                        )
                    if len(discovered) >= self.maximum_file_count:
                        raise RepositoryLimitExceededError("Repository file count limit exceeded.")
                    total_size += stat.st_size
                    if total_size > self.maximum_repository_size:
                        raise RepositoryLimitExceededError("Repository size limit exceeded.")
                    binary = is_binary_file(path)
                    digest = None if binary else hashlib.sha256()
                    if digest is not None:
                        with path.open("rb") as handle:
                            hashed_size = 0
                            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                                hashed_size += len(chunk)
                                if hashed_size > self.maximum_file_size:
                                    raise RepositoryLimitExceededError(
                                        "File exceeded maximum size during hashing."
                                    )
                                digest.update(chunk)
                    technologies = self._technology_names(relative)
                    language = LANGUAGE_EXTENSIONS.get(relative.suffix.lower())
                    if relative.name.lower() == "pyproject.toml":
                        language = "Python"
                    elif relative.name.lower() == "requirements.txt":
                        language = "Python"
                    elif relative.name.lower() == "angular.json":
                        language = "JSON/Angular"
                    elif relative.name.lower() == "package.json":
                        language = "JSON"
                    discovered.append(RepositoryFile(
                        relative_path=relative.as_posix(),
                        file_name=relative.name,
                        extension=relative.suffix.lower(),
                        size_bytes=stat.st_size,
                        content_hash=digest.hexdigest() if digest else None,
                        is_binary=binary,
                        language=language,
                        technologies=technologies,
                    ))
                except RepositoryLimitExceededError:
                    raise
                except RepositorySecurityError:
                    raise
                except (PermissionError, OSError):
                    logger.warning(
                        "event=repository_file_discovery_unreadable relative_path=%s",
                        relative.as_posix(),
                    )
                    continue

        logger.info(
            "event=repository_file_discovery_completed total_files=%s total_size_bytes=%s",
            len(discovered), total_size,
        )
        return discovered


def discover_repository_files(repository_root: str | Path, **kwargs) -> list[RepositoryFile]:
    return FileDiscovery(**kwargs).discover(repository_root)
