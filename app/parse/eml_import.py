from __future__ import annotations

from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime

from ..schemas import Dataset
from .email_text import parse_email_text


def eml_to_text(raw: bytes) -> str:
    """Extract subject + best body + a parseable date line from a .eml file.

    Chase/Venmo alerts often carry the amount or merchant in the subject, so we
    include it. The Date header is normalized to 'Mon D, YYYY' so the downstream
    parser's date matcher can pick it up."""
    msg = BytesParser(policy=policy.default).parsebytes(raw)
    parts: list[str] = []

    subject = msg.get("subject")
    if subject:
        parts.append(str(subject))

    body = None
    try:
        body = msg.get_body(preferencelist=("plain", "html"))
    except Exception:
        body = None

    if body is not None:
        try:
            parts.append(body.get_content())
        except Exception:
            pass
    else:  # fallback: walk parts for any text
        for part in msg.walk():
            if part.get_content_type() in ("text/plain", "text/html"):
                try:
                    parts.append(part.get_content())
                except Exception:
                    continue

    date_hdr = msg.get("date")
    if date_hdr:
        try:
            parts.append("on " + parsedate_to_datetime(date_hdr).strftime("%b %-d, %Y"))
        except Exception:
            pass

    return "\n".join(p for p in parts if p)


def parse_eml(raw: bytes) -> Dataset:
    return parse_email_text(eml_to_text(raw))
