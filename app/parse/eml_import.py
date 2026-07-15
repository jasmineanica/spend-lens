from __future__ import annotations

import re
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime

from ..schemas import Dataset
from .email_text import parse_email_text

# Split an mbox before each envelope "From " line (line at column 0 starting with
# "From " and ending in a 4-digit year). Well-formed mbox escapes body lines as
# ">From ", so this reliably separates messages without writing to disk.
_MBOX_BOUNDARY = re.compile(rb"\n(?=From .+\d{4}\r?\n)")
_MAX_MBOX_MESSAGES = 20000  # safety cap for very large exports


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


def _split_mbox(raw: bytes) -> list[bytes]:
    """Split mbox bytes into individual message bodies (envelope line removed)."""
    chunks = _MBOX_BOUNDARY.split(b"\n" + raw)
    messages: list[bytes] = []
    for chunk in chunks:
        chunk = chunk.lstrip(b"\r\n")
        if chunk.startswith(b"From "):  # drop the non-RFC822 envelope line
            nl = chunk.find(b"\n")
            chunk = chunk[nl + 1:] if nl != -1 else b""
        if chunk.strip():
            messages.append(chunk)
    return messages


def parse_mbox(raw: bytes) -> Dataset:
    """Parse an mbox export (e.g. Google Takeout). Each message is parsed on its
    own so per-message dates are preserved; non-transaction emails yield nothing."""
    txns = []
    investments = []
    for msg in _split_mbox(raw)[:_MAX_MBOX_MESSAGES]:
        ds = parse_eml(msg)
        txns.extend(ds.transactions)
        investments.extend(ds.investments)
    return Dataset(transactions=txns, investments=investments)
