"""Reply addresses and reply text (P2-04, ADR-037).

Each outreach email replies to `reply+<message id><mac>@<inbound domain>`: the message it
answers, and a short HMAC so nobody can make up an address that lands on someone's lead. It
fits the 64 characters an address's local part may have, in lowercase, which mail systems keep.
"""

import hashlib
import hmac
import html
import re
from uuid import UUID

from cornerpin.core.config import get_settings

MAC_LENGTH = 16
ADDRESS = re.compile(r"^reply\+([0-9a-f]{32})([0-9a-f]{16})@", re.IGNORECASE)
# Where quoted history starts, in the forms the common mail clients write it.
QUOTE_STARTS = (
    re.compile(r"^On .+ wrote:\s*$"),
    re.compile(r"^-{2,}\s*Original Message\s*-{2,}", re.IGNORECASE),
    re.compile(r"^_{8,}\s*$"),
)
# Outlook's quoted header: "From: ..." with "Sent:", "Date:" or "To:" on the next line.
HEADER_FROM = re.compile(r"^From:\s.+", re.IGNORECASE)
HEADER_NEXT = re.compile(r"^(Sent|Date|To):\s", re.IGNORECASE)
SENT_FROM = re.compile(r"^Sent from my \w+", re.IGNORECASE)
MAX_REPLY_CHARS = 10_000


def _mac(message_id: UUID) -> str:
    key = get_settings().secret_key.encode()
    return hmac.new(key, message_id.hex.encode(), hashlib.sha256).hexdigest()[:MAC_LENGTH]


def reply_address(message_id: UUID, domain: str) -> str:
    return f"reply+{message_id.hex}{_mac(message_id)}@{domain}"


def message_for(address: str) -> UUID | None:
    """The outreach message a reply address belongs to, if it's one of ours and untampered."""
    found = ADDRESS.match(address.strip().strip("<>"))
    if found is None:
        return None
    message_id = UUID(found.group(1).lower())
    return message_id if hmac.compare_digest(found.group(2).lower(), _mac(message_id)) else None


def html_to_text(markup: str) -> str:
    """Enough of an HTML email's text to read: line breaks kept, tags dropped."""
    markup = re.sub(r"(?is)<(script|style)\b.*?</\1>", "", markup)
    markup = re.sub(r"(?i)<br\s*/?>|</(p|div|li|tr|h[1-6])>", "\n", markup)
    return html.unescape(re.sub(r"<[^>]+>", "", markup))


def reply_text(text: str) -> str:
    """What the buyer wrote, without the quoted history below it or a "Sent from my phone"."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    kept: list[str] = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        following = lines[index + 1].strip() if index + 1 < len(lines) else ""
        if (
            any(p.match(stripped) for p in QUOTE_STARTS)
            or QUOTE_STARTS[0].match(f"{stripped} {following}")  # "On ..." wrapped before "wrote:"
            or (HEADER_FROM.match(stripped) and HEADER_NEXT.match(following))
        ):
            break
        if stripped.startswith(">") or SENT_FROM.match(stripped):
            continue
        kept.append(line.rstrip())
    reply = "\n".join(kept).strip()
    # A reply that is all quote (a forward, say) keeps everything rather than nothing.
    return (reply or text.strip())[:MAX_REPLY_CHARS]
