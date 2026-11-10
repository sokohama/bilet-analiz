"""Takvim ekran görüntüsünden (Aviasales, Skyscanner vb.) tarih/fiyat çıkarır.

Anthropic görsel okuma kullanır; API anahtarı gerekir.
"""
import base64
import io
import os
from datetime import date, timedelta

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")
MAX_BYTES = 4_500_000


class ExtractError(Exception):
    pass


TOOL = {
    "name": "record_prices",
    "description": "Takvimdeki her gün için bilet fiyatını kaydeder.",
    "input_schema": {
        "type": "object",
        "properties": {
            "origin": {"type": "string", "description": "Kalkış şehri, görünüyorsa"},
            "destination": {"type": "string", "description": "Varış şehri, görünüyorsa"},
            "currency": {"type": "string", "description": "Para birimi, görünüyorsa"},
            "prices": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "date": {"type": "string", "description": "Kalkış tarihi, YYYY-MM-DD"},
                        "price": {"type": "number"},
                    },
                    "required": ["date", "price"],
                },
            },
        },
        "required": ["prices"],
    },
}


def _prepare(image_bytes: bytes, media_type: str):
    """Çok büyük görselleri API sınırına sığacak şekilde küçültür."""
    if len(image_bytes) <= MAX_BYTES:
        return image_bytes, media_type
    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img.thumbnail((2800, 2800))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=90)
    return out.getvalue(), "image/jpeg"


def _fix_year(d: date, snapshot: date):
    """Model yılı yanlış yazarsa düzeltir; geçmiş günleri atar."""
    if d >= snapshot:
        return d
    if d.year < snapshot.year:
        for y in (snapshot.year, snapshot.year + 1):
            try:
                cand = d.replace(year=y)
            except ValueError:
                continue
            if cand >= snapshot:
                return cand
    return None


def normalize(raw, snapshot: date):
    """Ham satırları temizler: tarih ayrıştırma, yıl düzeltme, tekrarları ayıklama."""
    rows = {}
    for r in raw:
        try:
            d = date.fromisoformat(str(r["date"])[:10])
            p = float(r["price"])
        except (KeyError, ValueError, TypeError):
            continue
        if p <= 0:
            continue
        d = _fix_year(d, snapshot)
        if d is None or d > snapshot + timedelta(days=400):
            continue
        rows[d] = p
    return [{"date": d, "price": p} for d, p in sorted(rows.items())]


def extract_prices(image_bytes: bytes, media_type: str, snapshot: date, api_key: str) -> dict:
    try:
        import anthropic
    except ImportError as e:
        raise ExtractError("anthropic paketi kurulu değil (requirements.txt'e bak).") from e
    if not api_key:
        raise ExtractError("API anahtarı yok.")

    data, mt = _prepare(image_bytes, media_type)
    prompt = (
        "This is a screenshot of a flight price calendar. Under each day number is the ticket "
        "price for that departure date; month names appear as headings (Azerbaijani, Turkish, "
        f"Russian or English). Today's date is {snapshot.isoformat()}. If no year is shown, choose "
        "the year so every date is on or after today. Skip days with no price (greyed out or "
        "empty). Read numbers exactly as shown and never guess a missing value. If the route or "
        "currency is visible, report them. Call record_prices."
    )
    client = anthropic.Anthropic(api_key=api_key)
    try:
        msg = client.messages.create(
            model=MODEL,
            max_tokens=4000,
            tools=[TOOL],
            tool_choice={"type": "tool", "name": "record_prices"},
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": mt,
                                "data": base64.b64encode(data).decode(),
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
    except anthropic.AuthenticationError as e:
        raise ExtractError("API anahtarı geçersiz.") from e
    except anthropic.APIError as e:
        raise ExtractError(f"API hatası: {e}") from e

    for block in msg.content:
        if getattr(block, "type", None) == "tool_use":
            out = block.input or {}
            prices = normalize(out.get("prices", []), snapshot)
            if not prices:
                break
            return {
                "prices": prices,
                "origin": out.get("origin"),
                "destination": out.get("destination"),
                "currency": out.get("currency"),
            }
    raise ExtractError("Fotoğraftan fiyat okunamadı. Takvimin net göründüğü bir ekran görüntüsü dene.")
