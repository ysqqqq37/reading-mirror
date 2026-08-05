#!/usr/bin/env python3
"""Deterministic Apple Notes date boundaries for original and generated text."""

from __future__ import annotations

import re
from datetime import datetime, tzinfo

from common import normalize_text


DATE_STAMP = re.compile(r"^(\d{4}年\d{2}月\d{2}号)(?:\s|$)")


class DateStampError(ValueError):
    pass


def canonical_for_leading_date(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ").lstrip()


def leading_date_stamp(value: str) -> str | None:
    match = DATE_STAMP.match(canonical_for_leading_date(value))
    return match.group(1) if match else None


def format_date(value: datetime) -> str:
    if value.tzinfo is None:
        raise DateStampError("Date stamps require a timezone-aware datetime")
    return value.strftime("%Y年%m月%d号")


def note_modification_date_stamp(value: str, *, local_timezone: tzinfo | None = None) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DateStampError("Apple Note modification_date is required for original-text dating")
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise DateStampError("Apple Note modification_date is not a valid ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise DateStampError("Apple Note modification_date is missing a timezone")
    localized = parsed.astimezone() if local_timezone is None else parsed.astimezone(local_timezone)
    return format_date(localized)


def should_date_original(plaintext: str) -> bool:
    return bool(normalize_text(plaintext)) and leading_date_stamp(plaintext) is None


def prepend_date(*, body_html: str, plaintext: str, stamp: str) -> tuple[str, str]:
    if not DATE_STAMP.fullmatch(stamp):
        raise DateStampError("Date stamp must use YYYY年MM月DD号")
    return f"<div>{stamp}</div><br><br>{body_html}", f"{stamp}\n\n{plaintext}"


def date_generated_fragment(*, content_html: str, content_plaintext: str, stamp: str) -> tuple[str, str]:
    if leading_date_stamp(content_plaintext) == stamp:
        return content_html, content_plaintext
    return prepend_date(body_html=content_html, plaintext=content_plaintext, stamp=stamp)
