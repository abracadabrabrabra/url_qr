import io
from typing import Optional
from PIL import Image, ImageDraw
import segno


def generate_simple_qr(url: str, scale: int = 10) -> bytes:
    qr = segno.make(url, error='H')
    buffer = io.BytesIO()
    qr.save(buffer, kind='png', scale=scale)
    return buffer.getvalue()


def generate_custom_color_qr(
        url: str,
        dark_color: str,
        light_color: str,
        scale: int = 10
) -> bytes:
    qr = segno.make(url, error='H')
    buffer = io.BytesIO()
    qr.save(
        buffer,
        kind='png',
        scale=scale,
        dark=dark_color,
        light=light_color
    )
    return buffer.getvalue()


def add_logo_to_qr(qr_bytes: bytes, logo_path: str) -> bytes:
    qr_img = Image.open(io.BytesIO(qr_bytes)).convert('RGB')
    with Image.open(logo_path) as logo:
        logo = logo.convert('RGBA')
        logo_size = qr_img.size[0] // 5
        logo = logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)

        circle_size = logo_size + 20
        mask = Image.new('RGBA', qr_img.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(mask)
        center = (qr_img.size[0] // 2, qr_img.size[1] // 2)
        draw.ellipse(
            [center[0] - circle_size // 2, center[1] - circle_size // 2,
             center[0] + circle_size // 2, center[1] + circle_size // 2],
            fill=(255, 255, 255, 200)
        )

        qr_img.paste(mask, (0, 0), mask)
        logo_pos = (center[0] - logo_size // 2, center[1] - logo_size // 2)
        qr_img.paste(logo, logo_pos, logo)

    result_buffer = io.BytesIO()
    qr_img.save(result_buffer, format='PNG')
    return result_buffer.getvalue()


def generate_qr_with_custom_params(
        url: str,
        scale: int = 10,
        dark_color: Optional[str] = None,
        light_color: Optional[str] = None,
        logo_path: Optional[str] = None
) -> bytes:
    if dark_color and light_color:
        qr_bytes = generate_custom_color_qr(url, dark_color, light_color, scale)
    else:
        qr_bytes = generate_simple_qr(url, scale)

    if logo_path:
        qr_bytes = add_logo_to_qr(qr_bytes, logo_path)

    return qr_bytes