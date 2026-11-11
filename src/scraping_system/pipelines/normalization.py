"""Conservative normalization; malformed values are rejected, never guessed."""

import re
import unicodedata
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit, urlunsplit


def normalize_whitespace(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Expected text")
    return " ".join(unicodedata.normalize("NFC", value).split())


def normalize_url(value: str) -> str:
    parts = urlsplit(normalize_whitespace(value))
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise ValueError("Expected an absolute HTTP(S) URL")
    if parts.username or parts.password or any(c.isspace() for c in parts.netloc + parts.path):
        raise ValueError("Invalid URL authority or whitespace")
    host = parts.hostname.lower().encode("idna").decode("ascii")
    if ":" in host:
        host = f"[{host}]"
    port = parts.port
    scheme = parts.scheme.lower()
    authority = host if port in (None, 80 if scheme == "http" else 443) else f"{host}:{port}"
    return urlunsplit((scheme, authority, parts.path or "/", parts.query, ""))


def normalize_currency(value: str) -> str:
    value = normalize_whitespace(value).upper()
    currencies = {"£": "GBP", "GBP": "GBP", "$": "USD", "USD": "USD", "€": "EUR", "EUR": "EUR"}
    if value not in currencies:
        raise ValueError(f"Unsupported currency: {value!r}")
    return currencies[value]


def parse_price(value: str | Decimal | int | float) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("A boolean is not a price")
    if isinstance(value, str):
        text = normalize_whitespace(value)
        text = re.sub(r"^(?:£|\$|€|GBP\s*|USD\s*|EUR\s*)", "", text).strip()
        if not re.fullmatch(r"(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d{1,2})?", text):
            raise ValueError(f"Invalid price: {value!r}")
        value = text.replace(",", "")
    try:
        price = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Invalid price") from exc
    if (
        not price.is_finite()
        or price < 0
        or price >= Decimal("10000000000")
        or price.as_tuple().exponent < -2
    ):
        raise ValueError("Price must be finite, nonnegative, and have at most two decimal places")
    return price.quantize(Decimal("0.01"))


def parse_rating(value: str | int) -> int:
    if isinstance(value, bool):
        raise ValueError("Invalid rating")
    words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
    if isinstance(value, str):
        text = normalize_whitespace(value).lower().removeprefix("star-rating ")
        value = words.get(text, int(text) if text.isdigit() else 0)
    if not isinstance(value, int) or value not in range(1, 6):
        raise ValueError("Rating must be 1–5 or One–Five")
    return value
