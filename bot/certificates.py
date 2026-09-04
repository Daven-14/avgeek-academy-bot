"""Certificate formatting and optional PNG generation."""

from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

from bot import db


def format_certificates_html(
    user_id: int, first_name: str | None
) -> str:
    certs = db.list_certificates(user_id)
    name = (first_name or "Aviator").strip() or "Aviator"
    if not certs:
        return (
            f"🏅 <b>Certificates</b>\n\n"
            f"No certificates yet, {name}.\n\n"
            "Complete <b>all lessons</b> in a module and score at least "
            "<b>80%</b> on its quiz to earn a certificate."
        )
    lines = [
        f"🏅 <b>Certificates — {name}</b>\n",
        f"You have earned <b>{len(certs)}</b> certificate(s):\n",
    ]
    for c in certs:
        awarded = str(c.get("awarded_at") or "")
        try:
            dt = datetime.fromisoformat(awarded)
            when = dt.strftime("%Y-%m-%d")
        except ValueError:
            when = awarded[:10] if awarded else "—"
        lines.append(
            f"• <b>{c['title']}</b>\n"
            f"  Awarded {when} UTC · module <code>{c['module_id']}</code>"
        )
    lines.append(
        "\n<i>Teaching aid only — not a license, type rating, or official credential.</i>"
    )
    return "\n".join(lines)


def render_certificate_png(
    first_name: str | None, module_title: str, awarded_at: str
) -> bytes | None:
    """Generate a simple certificate PNG. Returns None if Pillow fails."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return None

    name = (first_name or "Aviator").strip() or "Aviator"
    try:
        dt = datetime.fromisoformat(awarded_at)
        when = dt.strftime("%Y-%m-%d")
    except ValueError:
        when = awarded_at[:10] if awarded_at else ""

    w, h = 900, 600
    img = Image.new("RGB", (w, h), (12, 28, 48))
    draw = ImageDraw.Draw(img)

    # Border
    draw.rectangle([20, 20, w - 20, h - 20], outline=(212, 175, 55), width=4)
    draw.rectangle([32, 32, w - 32, h - 32], outline=(180, 200, 220), width=1)

    try:
        font_title = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 42
        )
        font_body = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28
        )
        font_small = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20
        )
    except OSError:
        font_title = ImageFont.load_default()
        font_body = font_title
        font_small = font_title

    def center(text: str, y: int, font, fill=(240, 245, 250)) -> None:
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        draw.text(((w - tw) / 2, y), text, font=font, fill=fill)

    center("AvGeek Academy", 80, font_title, fill=(212, 175, 55))
    center("Certificate of Completion", 150, font_body)
    center("This certifies that", 230, font_small, fill=(180, 200, 220))
    center(name, 280, font_title, fill=(255, 255, 255))
    center("completed the module", 350, font_small, fill=(180, 200, 220))
    center(module_title, 400, font_body, fill=(120, 200, 255))
    center(f"Awarded {when} UTC", 480, font_small, fill=(180, 200, 220))
    center("Teaching aid only — not an official credential", 530, font_small, fill=(140, 160, 180))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def cert_png_path_for_cache(module_id: str) -> Path:
    from bot.config import DATA_DIR

    return DATA_DIR / "certs_cache" / f"{module_id}.png"
