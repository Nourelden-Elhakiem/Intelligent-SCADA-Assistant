"""Safe file helpers for pipeline artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, TypeAlias, cast

import numpy as np
import numpy.typing as npt

FloatArray: TypeAlias = npt.NDArray[np.float32]


class ArtifactError(RuntimeError):
    """Raised when an intermediate pipeline artifact is invalid or unavailable."""


def read_json(path: Path) -> Any:
    if not path.exists():
        raise ArtifactError(f"Artifact not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArtifactError(f"Could not read JSON artifact {path}: {exc}") from exc


def read_json_records(path: Path) -> list[dict[str, Any]]:
    data = read_json(path)
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise ArtifactError(f"Expected a list of records in {path}")
    return cast(list[dict[str, Any]], data)


def write_json(path: Path, data: Any) -> None:
    """Write formatted UTF-8 JSON atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        Path(temp_name).replace(path)
    except Exception:
        Path(temp_name).unlink(missing_ok=True)
        raise


def save_embeddings(path: Path, embeddings: FloatArray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".npy", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            np.save(handle, embeddings)
            handle.flush()
            os.fsync(handle.fileno())
        Path(temp_name).replace(path)
    except Exception:
        Path(temp_name).unlink(missing_ok=True)
        raise


def load_embeddings(path: Path) -> FloatArray:
    if not path.exists():
        raise ArtifactError(f"Embeddings not found: {path}")
    try:
        array = np.load(path, allow_pickle=False)
        if not isinstance(array, np.ndarray) or array.ndim != 2:
            raise ValueError("Expected a 2D array")
        return cast(FloatArray, np.asarray(array, dtype=np.float32))
    except (OSError, ValueError, TypeError) as exc:
        raise ArtifactError(f"Invalid embeddings artifact: {path.name}") from exc


def require_fields(records: Iterable[dict[str, Any]], fields: set[str], name: str) -> None:
    for index, record in enumerate(records):
        missing = fields - record.keys()
        if missing:
            joined = ", ".join(sorted(missing))
            raise ArtifactError(f"{name} record {index} is missing fields: {joined}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def outputs_ready(paths: Iterable[Path]) -> bool:
    return all(path.exists() and path.stat().st_size > 0 for path in paths)


def json_digest(value: Any) -> str:
    """Hash structured content independent of JSON formatting or dictionary order."""
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def write_stage_manifest(
    path: Path, inputs: Mapping[str, Any], outputs: Sequence[Path], *, root: Path
) -> None:
    root = root.resolve()
    records = {str(p.resolve().relative_to(root).as_posix()): sha256_file(p) for p in outputs}
    write_json(path, {"version": 1, "inputs": dict(inputs), "outputs": records})


def stage_matches(
    path: Path, inputs: Mapping[str, Any], required_outputs: Sequence[Path], *, root: Path
) -> bool:
    """Unversioned, changed or incomplete outputs are never a valid resume point."""
    try:
        root = root.resolve()
        manifest = read_json(path)
        if not isinstance(manifest, dict) or manifest.get("version") != 1:
            return False
        if json_digest(manifest.get("inputs")) != json_digest(inputs):
            return False
        records = manifest.get("outputs")
        if not isinstance(records, dict) or not records:
            return False
        required = {p.resolve().relative_to(root).as_posix() for p in required_outputs}
        if not required <= records.keys():
            return False
        for relative, digest in records.items():
            output = (root / relative).resolve()
            if not output.is_relative_to(root) or not output.is_file():
                return False
            if sha256_file(output) != digest:
                return False
        return True
    except (ArtifactError, OSError, ValueError, TypeError):
        return False
