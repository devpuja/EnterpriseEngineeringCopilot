import os
import shutil
import subprocess
import tempfile
from pathlib import Path


class DiagramRenderer:
    def __init__(
        self,
        mermaid_cli: str | None = None,
        timeout_seconds: float = 30.0,
        executable_path: str | None = None,
    ):
        configured = executable_path or mermaid_cli or os.getenv("MERMAID_CLI_PATH")
        if configured:
            self.executable = configured
        else:
            self.executable = shutil.which("mmdc") or ""
        self.timeout_seconds = timeout_seconds

    def is_available(self) -> bool:
        if not self.executable:
            return False
        return Path(self.executable).is_file() or shutil.which(self.executable) is not None

    def render_svg(self, mermaid_source: str) -> str | None:
        return self._render(mermaid_source, "svg")

    def render_png(self, mermaid_source: str) -> bytes | None:
        return self._render(mermaid_source, "png")

    def _render(self, mermaid_source: str, output_format: str) -> str | bytes | None:
        if not self.is_available():
            return None
        if not mermaid_source.strip():
            return None
        with tempfile.TemporaryDirectory(prefix="eec-mermaid-") as directory:
            temp_dir = Path(directory)
            input_path = temp_dir / "diagram.mmd"
            output_path = temp_dir / f"diagram.{output_format}"
            input_path.write_text(mermaid_source, encoding="utf-8")
            command = [
                self.executable,
                "-i",
                str(input_path),
                "-o",
                str(output_path),
            ]
            try:
                subprocess.run(
                    command,
                    check=True,
                    capture_output=True,
                    timeout=self.timeout_seconds,
                    text=True,
                )
            except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired):
                return None
            if not output_path.is_file():
                return None
            data = output_path.read_bytes()
            if output_format == "svg":
                text = data.decode("utf-8", errors="replace")
                if "<script" in text.lower() or "javascript:" in text.lower():
                    return None
                return text
            if data.startswith(b"\x89PNG\r\n\x1a\n"):
                return data
        return None
