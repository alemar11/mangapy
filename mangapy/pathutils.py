import hashlib
import re
import stat
import unicodedata
from pathlib import Path

MAX_FILENAME_COMPONENT_BYTES = 180

_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


def sanitize_filename_component(value: object, fallback: str = "unknown") -> str:
    normalized = unicodedata.normalize("NFKC", str(value)).strip()
    sanitized = "".join(
        "_" if char in '<>:"/\\|?*' or unicodedata.category(char).startswith("C") else char for char in normalized
    )
    sanitized = re.sub(r"\s+", " ", sanitized)
    sanitized = re.sub(r"_+", "_", sanitized).strip(" ._")
    if not sanitized or sanitized in {".", ".."}:
        sanitized = fallback

    if sanitized.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES:
        sanitized = f"_{sanitized}"
    return limit_filename_component(sanitized)


def limit_filename_component(value: str) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= MAX_FILENAME_COMPONENT_BYTES:
        return value

    digest = hashlib.sha256(encoded).hexdigest()[:12]
    prefix_budget = MAX_FILENAME_COMPONENT_BYTES - len(digest) - 1
    prefix = ""
    prefix_size = 0
    for char in value:
        char_size = len(char.encode("utf-8"))
        if prefix_size + char_size > prefix_budget:
            break
        prefix += char
        prefix_size += char_size
    prefix = prefix.rstrip(" ._") or "item"
    return f"{prefix}-{digest}"


def ensure_real_subdirectory(root: str | Path, *parts: str) -> Path:
    root_path = Path(root).expanduser()
    root_path.mkdir(parents=True, exist_ok=True)
    root_metadata = root_path.lstat()
    if stat.S_ISLNK(root_metadata.st_mode) or not stat.S_ISDIR(root_metadata.st_mode):
        raise OSError(f"Output path is not a real directory: {root_path}")
    resolved_root = root_path.resolve(strict=True)
    if not resolved_root.is_dir():
        raise NotADirectoryError(f"Output path is not a directory: {root_path}")

    current = resolved_root
    for part in parts:
        if not part or Path(part).name != part or part in {".", ".."}:
            raise OSError(f"Unsafe output path component: {part!r}")
        candidate = current / part
        try:
            candidate.mkdir()
        except FileExistsError:
            pass
        metadata = candidate.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise OSError(f"Output path is not a real directory: {candidate}")
        resolved_candidate = candidate.resolve(strict=True)
        if resolved_candidate != resolved_root and resolved_root not in resolved_candidate.parents:
            raise OSError(f"Output path escapes the configured root: {candidate}")
        current = candidate
    return current
