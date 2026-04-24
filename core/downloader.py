"""Shared HTTP download utilities for the deTilda pipeline.

Centralises SSL-fallback fetching used by assets.py, fonts_localizer.py
and checker.py so the logic lives in one place.
"""
from __future__ import annotations

import contextlib
import ssl
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from core import logger

__all__ = [
    "fetch_bytes",
    "fetch_text",
    "resolve_download_folder",
    "download_to_project",
]

_DEFAULT_UA = "deTilda/1.0"
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

_SSL_FALLBACK_CONTEXT: ssl.SSLContext | None = None


def _get_unverified_context() -> ssl.SSLContext:
    global _SSL_FALLBACK_CONTEXT
    if _SSL_FALLBACK_CONTEXT is None:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        _SSL_FALLBACK_CONTEXT = ctx
    return _SSL_FALLBACK_CONTEXT


def _normalize_url(url: str) -> str:
    """Ensure protocol-relative URLs have an explicit scheme."""
    return f"https:{url}" if url.startswith("//") else url


def fetch_bytes(url: str, *, user_agent: str = _DEFAULT_UA, timeout: int = 20) -> tuple[bytes, bool]:
    """Download *url* and return ``(data, ssl_bypassed)``.

    On SSL error retries once with certificate verification disabled.
    """
    normalized = _normalize_url(url)
    request = urllib.request.Request(
        normalized,
        headers={"User-Agent": user_agent, "Accept": "*/*"},
    )
    try:
        with contextlib.closing(urllib.request.urlopen(request, timeout=timeout)) as resp:  # type: ignore[arg-type]
            return resp.read(), False
    except urllib.error.URLError as exc:
        if not isinstance(getattr(exc, "reason", None), ssl.SSLError):
            raise
    except ssl.SSLError:
        pass

    logger.warn(f"[downloader] SSL-проверка не удалась для {normalized}, повтор без проверки")
    with contextlib.closing(
        urllib.request.urlopen(request, timeout=timeout, context=_get_unverified_context())  # type: ignore[arg-type]
    ) as resp:
        return resp.read(), True


def fetch_text(url: str, *, user_agent: str = _BROWSER_UA, timeout: int = 20) -> str:
    """Download *url* as UTF-8 text."""
    data, _ = fetch_bytes(url, user_agent=user_agent, timeout=timeout)
    return data.decode("utf-8", errors="replace")


def resolve_download_folder(url: str, rules: list[dict]) -> tuple[str, str] | None:
    """Return ``(folder, filename)`` for *url* based on extension rules.

    Returns ``None`` if no rule matches.
    """
    parsed = urllib.parse.urlsplit(_normalize_url(url))
    if parsed.scheme not in {"http", "https"}:
        return None
    filename = Path(urllib.parse.unquote(parsed.path)).name
    if not filename:
        return None
    suffix = Path(filename).suffix.lower()
    for rule in rules:
        folder = str(rule.get("folder", "")).strip().strip("/")
        if not folder:
            continue
        extensions = rule.get("extensions")
        if extensions:
            exts = {str(e).lower() for e in extensions if isinstance(e, str)}
            if suffix not in exts:
                continue
        return folder, filename
    return None


def download_to_project(
    url: str,
    project_root: Path,
    rules: list[dict],
) -> tuple[Path, bool] | None:
    """Download *url* into the project folder determined by *rules*.

    Returns ``(destination_path, ssl_bypassed)`` on success, ``None`` on failure
    or if no matching rule exists.
    """
    target = resolve_download_folder(url, rules)
    if target is None:
        return None
    folder, filename = target
    destination = project_root / folder / filename
    if destination.exists():
        return destination, False
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        data, ssl_bypassed = fetch_bytes(url)
        destination.write_bytes(data)
        logger.info(f"🌐 Загружен ресурс: {url} → {folder}/{filename}")
        return destination, ssl_bypassed
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        logger.warn(f"[downloader] Не удалось скачать {url}: {exc}")
        return None
    except Exception as exc:
        logger.warn(f"[downloader] Неожиданная ошибка при скачивании {url}: {exc}")
        return None
