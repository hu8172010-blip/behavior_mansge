"""Strictly bounded, traceable dataset acquisition."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import http.client
import os
from pathlib import Path
import shutil
import threading
import urllib.request
import urllib.error
from urllib.parse import urlparse
from uuid import uuid4
import zipfile

from .config import DATA_ROOT, MAX_DATA_BYTES
from .sources import DatasetSource, SOURCES
from .storage import (
    StorageBudgetError,
    atomic_json_write,
    digest as _storage_digest,
    inside as _storage_inside,
    root_size as _storage_root_size,
)

FIRST_ROUND_KEYS = frozenset({"rlvs", "urfall", "avenue", "avenue_ground_truth"})
_CHUNK = 1024 * 1024
_GDOWN_LOCK = threading.Lock()
R3D18_WEIGHTS_URL = "https://download.pytorch.org/models/r3d_18-b3b3357e.pth"
R3D18_WEIGHTS_SIZE = 133_546_016
R3D18_WEIGHTS_SHA256 = "b3b3357ead25631ec9c57362ff2128a92d0427e01e2cd184951a44380c3f2e9d"


@dataclass(frozen=True, slots=True)
class DownloadResult:
    key: str
    files: tuple[Path, ...]
    source_url: str
    homepage: str = ""
    research_use_note: str = ""
    downloaded_at: datetime | None = None
    original_locator: str = ""
    root: Path | None = None
    file_urls: dict[str, str] | None = None


def _root_size(root: Path) -> int:
    return _storage_root_size(root)


def _check(root: Path, additional: int = 0) -> None:
    if additional < 0 or _root_size(root) + additional > MAX_DATA_BYTES:
        raise StorageBudgetError("Data-root budget would be exceeded.")


def _inside(root: Path, path: Path) -> Path:
    return _storage_inside(root, path)


def _digest(path: Path) -> str:
    return _storage_digest(path)


def _head(url: str) -> tuple[int, str, dict[str, str]]:
    with urllib.request.urlopen(urllib.request.Request(url, method="HEAD")) as response:
        value = response.headers.get("Content-Length")
        if value is None or not value.isdigit():
            raise StorageBudgetError("Server did not report a final file size.")
        return int(value), response.geturl() if hasattr(response, "geturl") else url, dict(response.headers)


def _integrity_path(target: Path) -> Path:
    return target.with_name(f".{target.name}.integrity.json")


def _read_integrity(target: Path) -> dict[str, object] | None:
    sidecar = _integrity_path(target)
    try:
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_integrity(
    target: Path,
    root: Path,
    *,
    url: str,
    resolved_url: str,
    size_bytes: int,
    checksum: str,
    etag: str | None,
) -> None:
    payload = {
        "url": url,
        "resolved_url": resolved_url,
        "size_bytes": size_bytes,
        "sha256": checksum,
        "etag": etag or "",
        "verified_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    atomic_json_write(
        _integrity_path(target),
        payload,
        managed_root=root,
        limit_bytes=MAX_DATA_BYTES,
    )


def _target_is_verified(
    target: Path,
    *,
    url: str,
    total: int,
    etag: str | None,
    expected_sha256: str | None,
) -> tuple[bool, str | None]:
    if not target.is_file() or target.stat().st_size != total:
        return False, None
    checksum = _digest(target)
    if expected_sha256 is not None:
        return checksum == expected_sha256, checksum
    integrity = _read_integrity(target)
    if integrity is None:
        return False, checksum
    recorded_etag = str(integrity.get("etag") or "")
    valid = (
        integrity.get("url") == url
        and integrity.get("size_bytes") == total
        and integrity.get("sha256") == checksum
        and (not etag or not recorded_etag or recorded_etag == etag)
    )
    return valid, checksum


def _http_download(
    url: str,
    root: Path,
    name: str,
    *,
    expected_sha256: str | None = None,
    expected_size: int | None = None,
) -> tuple[Path, str]:
    target, part = root / name, root / f"{name}.part"
    _inside(root, target)
    target.parent.mkdir(parents=True, exist_ok=True)
    total, head_resolved, head_headers = _head(url)
    if expected_size is not None and total != expected_size:
        raise IOError("Server Content-Length does not match the expected file size.")
    etag = head_headers.get("ETag") or head_headers.get("Etag")
    verified, checksum = _target_is_verified(
        target,
        url=url,
        total=total,
        etag=etag,
        expected_sha256=expected_sha256,
    )
    if verified and checksum is not None:
        _write_integrity(
            target,
            root,
            url=url,
            resolved_url=head_resolved,
            size_bytes=total,
            checksum=checksum,
            etag=etag,
        )
        return target, head_resolved
    resolved = head_resolved
    retryable = (OSError, http.client.IncompleteRead, urllib.error.URLError)
    for attempt in range(8):
        existing = part.stat().st_size if part.exists() else 0
        if existing > total:
            raise StorageBudgetError("Partial file is larger than the reported file.")
        _check(root, total - existing)
        if existing == total:
            checksum = _digest(part)
            if expected_sha256 is not None and checksum != expected_sha256:
                part.unlink()
                raise IOError("Downloaded file checksum does not match the expected SHA-256.")
            os.replace(part, target)
            _write_integrity(
                target,
                root,
                url=url,
                resolved_url=resolved,
                size_bytes=total,
                checksum=checksum,
                etag=etag,
            )
            return target, resolved
        headers = {"Range": f"bytes={existing}-"} if existing else {}
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers, method="GET")) as response:
                remaining = total - existing
                content_length = response.headers.get("Content-Length")
                if content_length is None or not content_length.isdigit() or int(content_length) != remaining:
                    raise IOError("GET Content-Length does not match the expected remaining bytes.")
                if existing:
                    content_range = response.headers.get("Content-Range", "")
                    expected = f"bytes {existing}-{total - 1}/{total}"
                    if content_range != expected:
                        raise IOError("GET Content-Range does not match the requested byte range.")
                resolved = response.geturl() if hasattr(response, "geturl") else url
                with part.open("ab") as out:
                    while remaining:
                        block = response.read(min(_CHUNK, remaining))
                        if not block:
                            raise IOError("Incomplete HTTP download; retained resumable part.")
                        _check(root, len(block))
                        out.write(block)
                        remaining -= len(block)
                    if response.read(1):
                        raise IOError("Server sent more bytes than it reported.")
        except retryable:
            if attempt == 7:
                raise
            continue
        checksum = _digest(part)
        if expected_sha256 is not None and checksum != expected_sha256:
            part.unlink()
            raise IOError("Downloaded file checksum does not match the expected SHA-256.")
        os.replace(part, target)
        _check(root)
        _write_integrity(
            target,
            root,
            url=url,
            resolved_url=resolved,
            size_bytes=total,
            checksum=checksum,
            etag=etag,
        )
        return target, resolved
    raise AssertionError("unreachable HTTP retry loop")


def ensure_pretrained_weights(root: Path = DATA_ROOT) -> Path:
    """Acquire torchvision R3D-18 weights through the bounded verifier."""
    relative = ".torch/hub/checkpoints/r3d_18-b3b3357e.pth"
    path, _ = _http_download(
        R3D18_WEIGHTS_URL,
        root,
        relative,
        expected_sha256=R3D18_WEIGHTS_SHA256,
        expected_size=R3D18_WEIGHTS_SIZE,
    )
    if path.stat().st_size != R3D18_WEIGHTS_SIZE or _digest(path) != R3D18_WEIGHTS_SHA256:
        raise IOError("Pretrained R3D-18 weights failed post-download verification.")
    _check(root)
    return path


def _download_kaggle(source: DatasetSource, root: Path) -> tuple[Path, ...]:
    api = f"https://www.kaggle.com/api/v1/datasets/view/{source.locator}"
    with urllib.request.urlopen(urllib.request.Request(api, method="GET")) as response:
        metadata = json.loads(response.read().decode("utf-8"))
    entries = metadata.get("datasetFiles") or metadata.get("files")
    sizes = []
    if isinstance(entries, list) and entries:
        for item in entries:
            value = item.get("totalBytes") if isinstance(item, dict) else None
            if not isinstance(value, int) or value < 0:
                raise StorageBudgetError("Kaggle file size is unknown or invalid.")
            sizes.append(value)
        projected = sum(sizes)
    else:
        projected = metadata.get("totalBytes")
        if not isinstance(projected, int) or projected <= 0:
            raise StorageBudgetError("Kaggle did not provide complete size metadata.")
    # KaggleHub can temporarily retain both the downloaded archive and extracted
    # files. Reserve twice the catalog size before allowing it to write.
    _check(root, projected * 2)
    import kagglehub
    cache = root / ".kagglehub"
    _inside(root, cache)
    location = Path(kagglehub.dataset_download(source.locator, output_dir=str(cache)))
    _inside(root, location)
    files = tuple(p for p in location.rglob("*") if p.is_file() and _inside(root, p))
    _check(root)
    return files


def _extract_zip_if_needed(archive: Path, root: Path, key: str) -> tuple[Path, ...]:
    if not zipfile.is_zipfile(archive):
        return (archive,)
    checksum = _digest(archive)
    destination = root / key
    staging = root / f".staging-{key}-{uuid4().hex}"
    try:
        with zipfile.ZipFile(archive) as zipped:
            members = zipped.infolist()
            size = sum(m.file_size for m in members)
            _check(root, size)
            for member in members:
                candidate = (staging / member.filename).resolve()
                if staging.resolve() not in candidate.parents and candidate != staging.resolve():
                    raise ValueError("Refusing zip member outside its destination.")
            staging.mkdir()
            for member in members:
                if member.is_dir():
                    continue
                output = staging / member.filename
                output.parent.mkdir(parents=True, exist_ok=True)
                with zipped.open(member) as inp, output.open("wb") as out:
                    shutil.copyfileobj(inp, out, _CHUNK)
        if _digest(archive) != checksum:
            raise IOError("Archive checksum changed during extraction.")
        if destination.exists():
            raise FileExistsError("Dataset destination already exists.")
        os.replace(staging, destination)
        _check(root)
        return (archive, *(p for p in destination.rglob("*") if p.is_file()))
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _bounded_gdown_download(
    source: DatasetSource,
    root: Path,
    total: int,
    *,
    expected_sha256: str | None = None,
) -> Path:
    """Run gdown with its target write path guarded by the managed-root cap."""
    archive, part = root / f"{source.key}.zip", root / f"{source.key}.zip.part"
    _inside(root, archive); _inside(root, part)
    if (
        archive.exists()
        and archive.stat().st_size == total
        and expected_sha256 is not None
        and _digest(archive) == expected_sha256
    ):
        return archive
    existing = part.stat().st_size if part.exists() else 0
    if existing > total:
        part.unlink()
        raise StorageBudgetError("Google Drive partial exceeds the confirmed length.")
    _check(root, total - existing)
    import gdown
    real_open = gdown.download.__globals__.get("open", __import__("builtins").open)

    class GuardedFile:
        def __init__(self, stream): self.stream = stream
        def write(self, data):
            _check(root, len(data))
            return self.stream.write(data)
        def __getattr__(self, name): return getattr(self.stream, name)
        def __enter__(self): self.stream.__enter__(); return self
        def __exit__(self, *args): return self.stream.__exit__(*args)

    def guarded_open(file, mode="r", *args, **kwargs):
        stream = real_open(file, mode, *args, **kwargs)
        try:
            managed = Path(file).resolve() == part.resolve()
        except TypeError:
            managed = False
        return GuardedFile(stream) if managed and any(flag in mode for flag in "wa+") else stream

    with _GDOWN_LOCK:
        had_open = "open" in gdown.download.__globals__
        previous = gdown.download.__globals__.get("open")
        gdown.download.__globals__["open"] = guarded_open
        try:
            output = gdown.download(id=source.locator, output=str(part), resume=True, quiet=False)
        except Exception:
            if part.exists() and (part.stat().st_size == 0 or part.stat().st_size > total or _root_size(root) > MAX_DATA_BYTES):
                part.unlink()
            raise
        finally:
            if had_open:
                gdown.download.__globals__["open"] = previous
            else:
                del gdown.download.__globals__["open"]
    invalid = not output or not part.is_file() or part.stat().st_size != total
    if not invalid and expected_sha256 is not None and _digest(part) != expected_sha256:
        invalid = True
    if invalid or _root_size(root) > MAX_DATA_BYTES:
        if part.exists() and (invalid or part.stat().st_size > total or _root_size(root) > MAX_DATA_BYTES):
            part.unlink()
        raise StorageBudgetError("Google Drive result did not match the bounded confirmed length.")
    os.replace(part, archive)
    _check(root)
    return archive


def _receipt_expected_sha256(root: Path, key: str, relative_path: str) -> str | None:
    receipt = root / "receipts" / key / "source.json"
    try:
        payload = json.loads(receipt.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    for item in payload.get("files", []):
        if (
            isinstance(item, dict)
            and item.get("path") == relative_path
            and isinstance(item.get("sha256"), str)
        ):
            return item["sha256"]
    return None


def verified_receipt_result(key: str, root: Path) -> DownloadResult | None:
    """Return a source result only when every receipt entry still verifies."""
    receipt_path = root / "receipts" / key / "source.json"
    try:
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    if payload.get("key") != key or not isinstance(payload.get("files"), list):
        return None
    files: list[Path] = []
    file_urls: dict[str, str] = {}
    for item in payload["files"]:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            return None
        try:
            target = _inside(root, root / item["path"])
        except (ValueError, OSError):
            return None
        if (
            not target.is_file()
            or target.stat().st_size != item.get("size_bytes")
            or _digest(target) != item.get("sha256")
        ):
            return None
        files.append(target)
        if isinstance(item.get("source_url"), str):
            file_urls[item["path"]] = item["source_url"]
    if not files:
        return None
    return DownloadResult(
        key=key,
        files=tuple(files),
        source_url=str(payload.get("source_url") or payload.get("homepage") or ""),
        homepage=str(payload.get("homepage") or ""),
        research_use_note=str(payload.get("research_use_note") or ""),
        original_locator=str(payload.get("original_locator") or ""),
        root=root,
        file_urls=file_urls,
    )


def migrate_http_integrity_from_receipt(key: str, root: Path) -> int:
    """Create checksum sidecars from an already verified receipt without I/O."""
    result = verified_receipt_result(key, root)
    if result is None:
        return 0
    written = 0
    for path in result.files:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
        url = (result.file_urls or {}).get(relative)
        if not url and key == "avenue" and path.name == Path(urlparse(SOURCES[key].locator).path).name:
            url = SOURCES[key].locator
        if not url:
            continue
        _write_integrity(
            path,
            root,
            url=url,
            resolved_url=url,
            size_bytes=path.stat().st_size,
            checksum=_digest(path),
            etag=None,
        )
        written += 1
    return written


def download_source(source: DatasetSource, root: Path = DATA_ROOT, *, allow_deferred: bool = False) -> DownloadResult:
    if not allow_deferred and (source.key not in FIRST_ROUND_KEYS or SOURCES.get(source.key) != source):
        raise ValueError("Source is not approved catalog metadata for the first-round acquisition.")
    _check(root); root.mkdir(parents=True, exist_ok=True)
    reused = verified_receipt_result(source.key, root)
    if reused is not None:
        migrate_http_integrity_from_receipt(source.key, root)
        return reused
    if source.method == "http":
        name = Path(urlparse(source.locator).path).name or f"{source.key}.download"
        expected = _receipt_expected_sha256(root, source.key, name)
        archive, resolved = _http_download(
            source.locator,
            root,
            name,
            expected_sha256=expected,
        )
        files = _extract_zip_if_needed(archive, root, source.key)
    elif source.method == "kaggle":
        files, resolved = _download_kaggle(source, root), f"https://www.kaggle.com/datasets/{source.locator}"
    elif source.method == "gdrive":
        confirmation_url = f"https://drive.google.com/uc?export=download&id={source.locator}"
        total, resolved, headers = _head(confirmation_url)
        disposition = headers.get("Content-Disposition", "").lower()
        content_type = headers.get("Content-Type", "").lower()
        if "attachment" not in disposition or "text/html" in content_type:
            raise StorageBudgetError("Google Drive did not resolve to a binary attachment.")
        archive_name = f"{source.key}.zip"
        archive = _bounded_gdown_download(
            source,
            root,
            total,
            expected_sha256=_receipt_expected_sha256(root, source.key, archive_name),
        )
        files = _extract_zip_if_needed(archive, root, source.key)
    else:
        raise ValueError(f"Unsupported acquisition method: {source.method}")
    result = DownloadResult(source.key, tuple(files), resolved, source.homepage, source.research_use_note,
                            datetime.now(timezone.utc), source.locator, root)
    write_source_receipt(result, root / "receipts" / source.key)
    _check(root)
    return result


def _receipt_text(result: DownloadResult) -> str:
    root = result.root.resolve() if result.root else None
    files = []
    for path in result.files:
        if not path.is_file(): continue
        if root: _inside(root, path)
        rel = path.resolve().relative_to(root).as_posix() if root else path.name
        item = {"path": rel, "size_bytes": path.stat().st_size, "sha256": _digest(path)}
        if result.file_urls and rel in result.file_urls:
            item["source_url"] = result.file_urls[rel]
        files.append(item)
    payload = {"key": result.key, "homepage": result.homepage, "source_url": result.source_url,
               "original_locator": result.original_locator or result.source_url,
               "downloaded_at_utc": (result.downloaded_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
               "research_use_note": result.research_use_note,
               "license_note": "Traceability metadata, not a legal determination.", "files": files}
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def write_source_receipt(result: DownloadResult, destination: Path | None = None) -> Path:
    destination = destination or Path.cwd() / result.key
    destination.mkdir(parents=True, exist_ok=True)
    receipt = destination / "source.json"
    payload = json.loads(_receipt_text(result))
    atomic_json_write(
        receipt,
        payload,
        managed_root=result.root,
        limit_bytes=MAX_DATA_BYTES,
    )
    return receipt
