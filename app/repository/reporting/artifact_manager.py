import re
import shutil
import uuid
from pathlib import Path
from uuid import UUID


class ArtifactManager:
    def __init__(
        self,
        output_root: str | Path,
        maximum_file_size_bytes: int = 50 * 1024 * 1024,
    ):
        self.output_root = Path(output_root).expanduser().resolve()
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.maximum_file_size_bytes = maximum_file_size_bytes

    @staticmethod
    def validate_output_directory(
        output_root: str | Path,
        protected_root: str | Path | None,
    ) -> None:
        if protected_root is None:
            return
        resolved_output = Path(output_root).expanduser().resolve()
        resolved_source = Path(protected_root).expanduser().resolve()
        if resolved_output == resolved_source or resolved_source in resolved_output.parents:
            raise ValueError("Artifact output must not be inside the source repository.")

    def safe_filename(self, report_id: UUID | str, extension: str) -> str:
        normalized_extension = extension.lower().lstrip(".")
        if not re.fullmatch(r"[a-z0-9]+", normalized_extension):
            raise ValueError("Unsupported artifact extension.")
        return f"architecture-report-{uuid.UUID(str(report_id))}.{normalized_extension}"

    def report_directory(self, report_id: UUID | str) -> Path:
        report_uuid = uuid.UUID(str(report_id))
        directory = self.output_root / str(report_uuid)
        if directory.exists() and (directory.is_symlink() or not directory.is_dir()):
            raise ValueError("Unsafe artifact directory.")
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def write_text(
        self,
        report_id: UUID | str,
        extension: str,
        content: str,
    ) -> tuple[Path, str, int]:
        filename = self.safe_filename(report_id, extension)
        directory = self.report_directory(report_id)
        destination = directory / filename
        data = content.encode("utf-8")
        return self._write_new(destination, data)

    def write_bytes(
        self,
        report_id: UUID | str,
        extension: str,
        content: bytes,
    ) -> tuple[Path, str, int]:
        filename = self.safe_filename(report_id, extension)
        directory = self.report_directory(report_id)
        destination = directory / filename
        return self._write_new(destination, content)

    def write_attachment(
        self,
        report_id: UUID | str,
        filename: str,
        content: bytes,
    ) -> tuple[Path, str, int]:
        if not re.fullmatch(r"diagram-[A-Za-z0-9_-]+\.(?:png|svg)", filename):
            raise ValueError("Unsupported report attachment filename.")
        directory = self.report_directory(report_id)
        return self._write_new(directory / filename, content)

    def _write_new(self, destination: Path, content: bytes) -> tuple[Path, str, int]:
        if len(content) > self.maximum_file_size_bytes:
            raise ValueError("Artifact exceeds the configured size limit.")
        resolved_destination = destination.resolve()
        if self.output_root not in resolved_destination.parents and resolved_destination != self.output_root:
            raise ValueError("Artifact path escapes the managed output directory.")
        with destination.open("xb") as handle:
            handle.write(content)
        relative = resolved_destination.relative_to(self.output_root).as_posix()
        return resolved_destination, relative, len(content)

    def cleanup_report(self, report_id: UUID | str) -> bool:
        directory = self.report_directory_for_cleanup(report_id)
        if directory is None or not directory.exists():
            return False
        resolved = directory.resolve()
        if self.output_root not in resolved.parents or resolved == self.output_root:
            raise ValueError("Refusing unsafe artifact cleanup.")
        quarantine = self.output_root / f".cleanup-{uuid.uuid4()}"
        resolved.rename(quarantine)
        shutil.rmtree(quarantine)
        return True

    def report_directory_for_cleanup(self, report_id: UUID | str) -> Path | None:
        try:
            report_uuid = uuid.UUID(str(report_id))
        except ValueError:
            return None
        directory = self.output_root / str(report_uuid)
        return directory if directory.is_dir() and not directory.is_symlink() else None
