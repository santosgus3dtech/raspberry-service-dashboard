from __future__ import annotations

import re


REDACTION_PATTERNS = (
    (
        re.compile(r"((?:hub\.verify_token|hub_verify_token|access_token)=)[^&\s\"]+"),
        r"\1<redacted>",
    ),
    (
        re.compile(r"((?:VERIFY_TOKEN|META_APP_SECRET|IG_ACCESS_TOKEN)=)\S+"),
        r"\1<redacted>",
    ),
    (
        re.compile(r"(Authorization:\s*Bearer\s+)\S+", re.IGNORECASE),
        r"\1<redacted>",
    ),
    (
        re.compile(r"\bIGAA[A-Za-z0-9_-]{20,}\b"),
        "<redacted-instagram-token>",
    ),
    (
        re.compile(r"(?i)\b(password|passwd|secret|token|api[_-]?key)=\S+"),
        r"\1=<redacted>",
    ),
)


def redact(value: str) -> str:
    redacted = value
    for pattern, replacement in REDACTION_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted
