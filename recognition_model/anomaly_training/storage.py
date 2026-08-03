"""Atomic writes with strict accounting for the managed data-root budget."""
from __future__ import annotations

from hashlib import sha256
from contextlib import contextmanager, nullcontext
import json
import os
from pathlib import Path
import time
from typing import Any, Iterator
from uuid import uuid4

from .config import MAX_DATA_BYTES

_CHUNK = 1024 * 1024


class StorageBudgetError(RuntimeError):
    """Raised before a write whose temporary or final state exceeds the cap."""


class ManagedArtifactLedger:
    """One aggregate cap across datasets, runs, models, and runtime jobs."""

    def __init__(
        self,
        roots: list[Path] | tuple[Path, ...],
        *,
        limit_bytes: int = MAX_DATA_BYTES,
        state_path: Path | None = None,
    ) -> None:
        if limit_bytes <= 0:
            raise ValueError("managed artifact limit must be positive")
        resolved = sorted(
            {Path(root).resolve() for root in roots},
            key=lambda path: len(path.parts),
        )
        self.roots: tuple[Path, ...] = tuple(
            path
            for path in resolved
            if not any(parent == path or parent in path.parents for parent in resolved if parent != path and len(parent.parts) < len(path.parts))
        )
        self.limit_bytes = limit_bytes
        self.state_path = (
            Path(state_path).resolve()
            if state_path is not None
            else None
        )
        self.lock_path = (
            self.state_path.with_suffix(self.state_path.suffix + ".lock")
            if self.state_path is not None
            else None
        )

    @property
    def total_bytes(self) -> int:
        total = sum(root_size(root) for root in self.roots)
        for bookkeeping in (self.state_path, self.lock_path):
            if (
                bookkeeping is not None
                and bookkeeping.is_file()
                and self.contains(bookkeeping)
            ):
                total -= bookkeeping.stat().st_size
        return max(0, total)

    @contextmanager
    def _locked_state(self) -> Iterator[dict[str, Any]]:
        if self.state_path is None or self.lock_path is None:
            yield {"schema_version": 1, "reservations": {}}
            return
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+b") as lock:
            if lock.tell() == 0:
                lock.write(b"\0")
                lock.flush()
            lock.seek(0)
            try:
                import msvcrt

                msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
                unlock = lambda: msvcrt.locking(
                    lock.fileno(), msvcrt.LK_UNLCK, 1
                )
            except ImportError:  # pragma: no cover - exercised on POSIX CI
                import fcntl

                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
                unlock = lambda: fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            try:
                try:
                    state = json.loads(
                        self.state_path.read_text(encoding="utf-8")
                    )
                except (FileNotFoundError, json.JSONDecodeError, OSError):
                    state = {"schema_version": 1, "reservations": {}}
                if not isinstance(state.get("reservations"), dict):
                    raise StorageBudgetError("Managed ledger is corrupt.")
                yield state
                self.state_path.parent.mkdir(parents=True, exist_ok=True)
                encoded = (
                    json.dumps(state, indent=2, sort_keys=True) + "\n"
                ).encode("utf-8")
                temp = self.state_path.with_name(
                    f".{self.state_path.name}.{uuid4().hex}.tmp"
                )
                try:
                    with temp.open("xb") as handle:
                        handle.write(encoded)
                        handle.flush()
                        os.fsync(handle.fileno())
                    _replace_with_retry(temp, self.state_path)
                finally:
                    temp.unlink(missing_ok=True)
            finally:
                lock.seek(0)
                unlock()

    @staticmethod
    def _reserved_bytes(state: dict[str, Any]) -> int:
        return sum(
            int(item["bytes"])
            for item in state["reservations"].values()
            if isinstance(item, dict) and isinstance(item.get("bytes"), int)
        )

    @contextmanager
    def reservation(
        self,
        temporary_bytes: int,
        *,
        replaced_path: Path | None = None,
        owner: str = "operation",
    ) -> Iterator[str]:
        if temporary_bytes < 0:
            raise StorageBudgetError("Negative storage reservation.")
        old_size = (
            replaced_path.stat().st_size
            if replaced_path is not None
            and replaced_path.is_file()
            and self.contains(replaced_path)
            else 0
        )
        token = uuid4().hex
        with self._locked_state() as state:
            current = self.total_bytes
            reserved = self._reserved_bytes(state)
            if max(
                current + reserved + temporary_bytes,
                current - old_size + reserved + temporary_bytes,
            ) > self.limit_bytes:
                raise StorageBudgetError(
                    "Managed artifact budget would be exceeded."
                )
            state["reservations"][token] = {
                "bytes": temporary_bytes,
                "owner": owner,
                "pid": os.getpid(),
                "created_at": time.time(),
            }
        try:
            yield token
        finally:
            with self._locked_state() as state:
                state["reservations"].pop(token, None)

    def contains(self, path: Path) -> bool:
        resolved = Path(path).resolve()
        return any(
            resolved == root or root in resolved.parents
            for root in self.roots
        )

    def reserve(
        self,
        temporary_bytes: int,
        *,
        replaced_path: Path | None = None,
    ) -> None:
        with self.reservation(
            temporary_bytes,
            replaced_path=replaced_path,
            owner="preflight",
        ):
            return

    def snapshot(self) -> dict[str, Any]:
        with self._locked_state() as state:
            reserved = self._reserved_bytes(state)
        return {
            "schema_version": 2,
            "limit_bytes": self.limit_bytes,
            "total_bytes": self.total_bytes,
            "reserved_bytes": reserved,
            "roots": [str(root) for root in self.roots],
            "state_path": (
                str(self.state_path) if self.state_path is not None else None
            ),
        }


def root_size(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file()) if root.exists() else 0


def inside(root: Path, path: Path) -> Path:
    resolved_root = root.resolve()
    resolved = path.resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise ValueError("Path is outside the managed data root.")
    return resolved


def digest(path: Path) -> str:
    hasher = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(_CHUNK), b""):
            hasher.update(block)
    return hasher.hexdigest()


def reserve_temporary_peak(
    root: Path,
    temporary_bytes: int,
    *,
    replaced_path: Path | None = None,
    limit_bytes: int = MAX_DATA_BYTES,
) -> None:
    """Check both the temporary peak and the final replacement state.

    A same-directory atomic replacement briefly retains the old destination
    while the complete temporary file exists, so the peak is current+temporary.
    """
    if temporary_bytes < 0:
        raise StorageBudgetError("Negative storage reservation.")
    current = root_size(root)
    old_size = (
        replaced_path.stat().st_size
        if replaced_path is not None and replaced_path.exists() and replaced_path.is_file()
        else 0
    )
    peak = current + temporary_bytes
    final = current - old_size + temporary_bytes
    if max(peak, final) > limit_bytes:
        raise StorageBudgetError("Data-root budget would be exceeded.")


def _replace_with_retry(temp: Path, target: Path) -> None:
    for attempt in range(5):
        try:
            os.replace(temp, target)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.05 * (attempt + 1))


def atomic_write_bytes(
    target: Path,
    data: bytes,
    *,
    managed_root: Path | None = None,
    limit_bytes: int = MAX_DATA_BYTES,
    artifact_ledger: ManagedArtifactLedger | None = None,
) -> None:
    if managed_root is not None:
        inside(managed_root, target)
        reserve_temporary_peak(
            managed_root,
            len(data),
            replaced_path=target,
            limit_bytes=limit_bytes,
        )
    reservation = (
        artifact_ledger.reservation(
            len(data),
            replaced_path=target,
            owner=f"atomic-write:{target.name}",
        )
        if artifact_ledger is not None
        else nullcontext()
    )
    with reservation:
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        try:
            with temp.open("xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            _replace_with_retry(temp, target)
        finally:
            temp.unlink(missing_ok=True)


def atomic_json_write(
    target: Path,
    payload: Any,
    *,
    managed_root: Path | None = None,
    limit_bytes: int = MAX_DATA_BYTES,
    artifact_ledger: ManagedArtifactLedger | None = None,
) -> None:
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    atomic_write_bytes(
        target,
        encoded,
        managed_root=managed_root,
        limit_bytes=limit_bytes,
        artifact_ledger=artifact_ledger,
    )


def atomic_text_write(
    target: Path,
    text: str,
    *,
    managed_root: Path | None = None,
    limit_bytes: int = MAX_DATA_BYTES,
    artifact_ledger: ManagedArtifactLedger | None = None,
) -> None:
    atomic_write_bytes(
        target,
        text.encode("utf-8"),
        managed_root=managed_root,
        limit_bytes=limit_bytes,
        artifact_ledger=artifact_ledger,
    )


def atomic_copy(
    source: Path,
    target: Path,
    *,
    managed_root: Path | None = None,
    limit_bytes: int = MAX_DATA_BYTES,
    artifact_ledger: ManagedArtifactLedger | None = None,
) -> None:
    size = source.stat().st_size
    if managed_root is not None:
        inside(managed_root, target)
        reserve_temporary_peak(
            managed_root,
            size,
            replaced_path=target,
            limit_bytes=limit_bytes,
        )
    reservation = (
        artifact_ledger.reservation(
            size,
            replaced_path=target,
            owner=f"atomic-copy:{target.name}",
        )
        if artifact_ledger is not None
        else nullcontext()
    )
    with reservation:
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        source_hash = sha256()
        copied_hash = sha256()
        try:
            with source.open("rb") as source_handle, temp.open("xb") as target_handle:
                while block := source_handle.read(_CHUNK):
                    source_hash.update(block)
                    target_handle.write(block)
                    copied_hash.update(block)
                target_handle.flush()
                os.fsync(target_handle.fileno())
            if source_hash.digest() != copied_hash.digest():
                raise OSError("Atomic copy verification failed.")
            _replace_with_retry(temp, target)
        finally:
            temp.unlink(missing_ok=True)
