import asyncio
import ipaddress
import os
import re
import shutil
import socket
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID, uuid4

from app.config.settings import settings
from app.repository.adapters.base import BaseRepositoryAdapter
from app.repository.exceptions import (
    InvalidRepositorySourceError,
    RepositoryNotFoundError,
    RepositorySecurityError,
    RepositoryLimitExceededError,
)
from app.repository.file_discovery import FileDiscovery
from app.repository.exclusions import RepositoryExclusions
from app.repository.models import RepositorySnapshot
from app.repository.workspace_manager import WorkspaceManager


class GitHubRepositoryAdapter(BaseRepositoryAdapter):
    OWNER_REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    OWNER_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
    REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")

    def __init__(self, workspace_manager: WorkspaceManager | None = None, git_executable: str | None = None):
        self.workspace_manager = workspace_manager or WorkspaceManager()
        self.git_executable = git_executable or settings.git_executable_path

    def parse_url(self, source_reference: str) -> tuple[str, str, str]:
        source = self._validate_nonempty_source(source_reference)
        parsed = urlparse(source)
        if parsed.scheme != "https":
            raise InvalidRepositorySourceError("Repository URL must use HTTPS.")
        try:
            port = parsed.port
        except ValueError as exc:
            raise InvalidRepositorySourceError("Repository URL port is invalid.") from exc
        if port not in (None, 443):
            raise InvalidRepositorySourceError("Repository URL must use HTTPS port 443.")
        host = (parsed.hostname or "").lower()
        if host not in {item.lower() for item in settings.github_allowed_hosts}:
            raise InvalidRepositorySourceError("Repository host is not approved.")
        if parsed.username or parsed.password:
            raise RepositorySecurityError("Repository credentials are not allowed in URLs.")
        try:
            address = ipaddress.ip_address(host)
            if address.is_private or address.is_loopback or address.is_link_local:
                raise RepositorySecurityError("Local-network Git hosts are not allowed.")
        except ValueError:
            pass
        if host != "github.com":
            try:
                resolved = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            except socket.gaierror as exc:
                raise RepositoryNotFoundError("Repository host could not be resolved.") from exc
            for result in resolved:
                try:
                    address = ipaddress.ip_address(result[4][0].split("%", 1)[0])
                except ValueError:
                    continue
                if (
                    address.is_private
                    or address.is_loopback
                    or address.is_link_local
                    or address.is_reserved
                    or address.is_unspecified
                    or address.is_multicast
                ):
                    raise RepositorySecurityError("Local-network Git hosts are not allowed.")
        if parsed.query or parsed.fragment or not parsed.path:
            raise InvalidRepositorySourceError("Repository URL format is invalid.")
        path_parts = parsed.path[1:].split("/") if parsed.path.startswith("/") else parsed.path.split("/")
        if len(path_parts) != 2:
            raise InvalidRepositorySourceError("Repository URL must contain an owner and repository name.")
        owner, repository = path_parts
        if not self.OWNER_PATTERN.fullmatch(owner):
            raise InvalidRepositorySourceError("Repository URL contains an invalid owner.")
        if not self.REPOSITORY_PATTERN.fullmatch(repository):
            raise InvalidRepositorySourceError("Repository URL contains an invalid repository name.")
        if repository.endswith(".git"):
            repository = repository[:-4]
        if not repository or not self.REPOSITORY_PATTERN.fullmatch(repository):
            raise InvalidRepositorySourceError("Repository URL contains an invalid repository name.")
        safe_url = f"https://{host}/{owner}/{repository}.git"
        return owner, repository, safe_url

    def _git(self, args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        git_path = shutil.which(self.git_executable) or self.git_executable
        try:
            git_env = os.environ.copy()
            git_env.update({
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_ASKPASS": "",
                "SSH_ASKPASS": "",
                "GIT_CONFIG_GLOBAL": os.devnull,
            })
            return subprocess.run(
                [git_path, *args],
                cwd=cwd,
                check=True,
                capture_output=True,
                text=True,
                timeout=300,
                env=git_env,
            )
        except FileNotFoundError as exc:
            raise RepositoryNotFoundError("Git executable is unavailable.") from exc
        except subprocess.TimeoutExpired as exc:
            raise RepositoryNotFoundError("Repository clone timed out.") from exc
        except subprocess.CalledProcessError as exc:
            raise RepositoryNotFoundError("Repository could not be cloned from GitHub.") from exc

    async def retrieve(
        self,
        source_reference: str,
        branch: str | None = None,
        analysis_id=None,
    ) -> RepositorySnapshot:
        owner, repository_name, clone_url = self.parse_url(source_reference)
        if branch and not re.fullmatch(r"[A-Za-z0-9._/-]+", branch):
            raise InvalidRepositorySourceError("Repository branch or reference is invalid.")
        analysis_uuid = UUID(str(analysis_id)) if analysis_id else uuid4()
        workspace = self.workspace_manager.create_workspace(analysis_uuid)
        workspace_id = self.workspace_manager.workspace_id_for_path(workspace) or uuid4()
        clone_directory = workspace / "repository"
        command = [
            "-c", "core.hooksPath=/dev/null",
            "-c", "protocol.file.allow=never",
            "-c", "http.followRedirects=initial",
            "clone", "--depth", "1", "--single-branch",
        ]
        if branch:
            if not re.fullmatch(r"[A-Za-z0-9._/-]+", branch):
                raise InvalidRepositorySourceError("Repository branch or reference is invalid.")
            command.extend(["--branch", branch])
        command.extend([clone_url, str(clone_directory)])
        try:
            await asyncio.to_thread(self._git, command)
            sha_result = await asyncio.to_thread(
                self._git, ["rev-parse", "HEAD"], clone_directory
            )
            commit_sha = sha_result.stdout.strip()
            if not re.fullmatch(r"[0-9a-f]{40,64}", commit_sha.lower()):
                raise RepositoryNotFoundError("Git returned an invalid commit SHA.")

            exclusions = RepositoryExclusions()
            total_size = 0
            total_count = 0
            for current_root, directories, filenames in os.walk(clone_directory, topdown=True, followlinks=False):
                current = Path(current_root)
                for directory_name in list(directories):
                    if (current / directory_name).is_symlink():
                        raise RepositorySecurityError("Symlinks are not allowed in cloned repositories.")
                directories[:] = [
                    name for name in directories
                    if not exclusions.is_excluded_directory(name)
                    and not (current / name).is_symlink()
                ]
                for filename in filenames:
                    path = current / filename
                    relative = path.relative_to(clone_directory)
                    if exclusions.is_excluded(relative.as_posix()):
                        continue
                    if path.is_symlink():
                        raise RepositorySecurityError("Symlinks are not allowed in cloned repositories.")
                    try:
                        stat = path.stat()
                        total_size += stat.st_size
                        total_count += 1
                        if stat.st_size > settings.maximum_repository_file_size_bytes:
                            raise RepositoryLimitExceededError("Repository individual file size limit exceeded.")
                        if total_size > settings.maximum_repository_size_bytes:
                            raise RepositoryLimitExceededError("Repository size limit exceeded.")
                        if total_count > settings.maximum_repository_file_count:
                            raise RepositoryLimitExceededError("Repository file count limit exceeded.")
                    except (PermissionError, OSError):
                        continue

            git_directory = clone_directory / ".git"
            if git_directory.exists() and not git_directory.is_symlink():
                shutil.rmtree(git_directory)
            elif git_directory.is_symlink():
                git_directory.unlink()

            for current_root, directories, filenames in os.walk(clone_directory, topdown=True, followlinks=False):
                current = Path(current_root)
                directories[:] = [
                    name for name in directories
                    if not exclusions.is_excluded_directory(name)
                    and not (current / name).is_symlink()
                ]
                for filename in filenames:
                    path = current / filename
                    relative = path.relative_to(clone_directory)
                    if exclusions.is_excluded(relative.as_posix()):
                        path.unlink(missing_ok=True)

            files = await asyncio.to_thread(FileDiscovery().discover, clone_directory)
            return RepositorySnapshot(
                analysis_id=analysis_uuid,
                source_type="github",
                repository_name=repository_name.removesuffix(".git"),
                source_reference=f"https://github.com/{owner}/{repository_name}",
                branch=branch,
                commit_sha=commit_sha,
                workspace_id=workspace_id,
                files=files,
                total_files=len(files),
                total_size_bytes=sum(file.size_bytes for file in files),
                created_at=datetime.now(timezone.utc),
            )
        except Exception:
            self.workspace_manager.cleanup_workspace(workspace)
            raise
