# app/services/qr_service.py
"""Genera imagen PNG de un código QR a partir de un texto (p. ej. URL)."""
import qrcode
import io


def generate_qr_png_bytes(data: str) -> bytes:
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
