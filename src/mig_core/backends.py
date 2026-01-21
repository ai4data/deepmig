"""Enhanced backends with encoding fallback for DeepMig.

This module provides backend wrappers that handle common encoding issues,
particularly when reading files that may have been created on Windows with
non-UTF-8 encodings (like Windows-1252).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from deepagents.backends.filesystem import FilesystemBackend


# Common encodings to try when UTF-8 fails
FALLBACK_ENCODINGS = [
    "utf-8",
    "utf-8-sig",  # UTF-8 with BOM
    "cp1252",     # Windows-1252 (Western European)
    "latin-1",    # ISO-8859-1 (fallback that accepts any byte)
]


class EncodingAwareFilesystemBackend(FilesystemBackend):
    """FilesystemBackend with automatic encoding fallback.

    This backend wraps the standard FilesystemBackend and adds encoding
    fallback handling. When reading a file fails with UTF-8, it tries
    other common encodings before giving up.

    This is particularly useful for:
    - YAML files created on Windows with smart quotes
    - Legacy files with Windows-1252 encoding
    - Files with BOM markers

    Args:
        root_dir: Root directory for the backend (optional).
        virtual_mode: Whether to use virtual path mode.
        fallback_encodings: List of encodings to try (default: common encodings).

    Example:
        ```python
        backend = EncodingAwareFilesystemBackend(
            root_dir=memories_dir,
            virtual_mode=True
        )
        ```
    """

    def __init__(
        self,
        root_dir: Path | str | None = None,
        virtual_mode: bool = False,
        fallback_encodings: list[str] | None = None,
    ) -> None:
        """Initialize the encoding-aware backend.

        Args:
            root_dir: Root directory for file operations.
            virtual_mode: Whether paths are virtual (relative to root_dir).
            fallback_encodings: List of encodings to try on decode failure.
        """
        super().__init__(root_dir=root_dir, virtual_mode=virtual_mode)
        # Store these explicitly since parent may not expose them as attributes
        self._root_dir = Path(root_dir) if root_dir else None
        self._virtual_mode = virtual_mode
        self.fallback_encodings = fallback_encodings or FALLBACK_ENCODINGS

    def read(
        self,
        path: str,
        offset: int | None = None,
        limit: int | None = None,
    ) -> str:
        """Read a file with automatic encoding fallback.

        Tries UTF-8 first, then falls back to other encodings if decoding fails.

        Args:
            path: Path to the file to read.
            offset: Line number to start reading from (1-indexed, optional).
            limit: Maximum number of lines to read (optional).

        Returns:
            File contents as a string.

        Raises:
            FileNotFoundError: If the file doesn't exist.
            UnicodeDecodeError: If all encoding attempts fail.
        """
        # Preserve original path for parent calls
        original_path = path

        # Resolve the actual file path
        if self._root_dir and self._virtual_mode:
            # Virtual mode: path is relative to root_dir
            rel_path = path[1:] if path.startswith("/") else path
            file_path = self._root_dir / rel_path
        elif self._root_dir:
            file_path = self._root_dir / path
        else:
            file_path = Path(path)

        # Check if file exists
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Check if it's a binary file (images, etc.)
        # Let parent handle binary files
        if self._is_binary_file(file_path):
            return super().read(original_path, offset=offset, limit=limit)

        # Try each encoding in order
        last_error = None
        for encoding in self.fallback_encodings:
            try:
                with open(file_path, "r", encoding=encoding) as f:
                    content = f.read()

                # If we used a fallback encoding, log it for awareness
                if encoding != "utf-8":
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.info(
                        f"File '{original_path}' was read using '{encoding}' encoding "
                        f"(UTF-8 failed). Consider re-saving as UTF-8."
                    )

                # Apply offset and limit if specified
                if offset is not None or limit is not None:
                    lines = content.splitlines(keepends=True)
                    start = (offset - 1) if offset and offset > 0 else 0
                    end = (start + limit) if limit else None
                    content = "".join(lines[start:end])

                return content

            except UnicodeDecodeError as e:
                last_error = e
                continue

        # All encodings failed
        raise UnicodeDecodeError(
            "all",
            b"",
            0,
            0,
            f"Failed to decode '{original_path}' with any of: {self.fallback_encodings}. "
            f"Last error: {last_error}"
        )

    def _is_binary_file(self, path: Path) -> bool:
        """Check if a file is likely binary based on extension.

        Args:
            path: Path to check.

        Returns:
            True if the file appears to be binary.
        """
        binary_extensions = {
            ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp",
            ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
            ".zip", ".tar", ".gz", ".7z", ".rar",
            ".exe", ".dll", ".so", ".dylib",
            ".pyc", ".pyo", ".class",
            ".sqlite", ".db",
        }
        return path.suffix.lower() in binary_extensions
