import io
from os import getcwd
from os.path import join

from qrcode.main import QRCode
from qrcode.constants import ERROR_CORRECT_H
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import RoundedModuleDrawer
from qrcode.image.styles.colormasks import RadialGradiantColorMask


def generate_qr_code(uid: str) -> bytes:
    qr = QRCode(
        error_correction=ERROR_CORRECT_H
    )
    qr.add_data("https://t.me/GlassMonitor1502Bot?start=" + uid)
    qr.make(fit=True)
    img = qr.make_image(
        image_factory=StyledPilImage,
        module_drawer=RoundedModuleDrawer(),
        color_mask=RadialGradiantColorMask(back_color=(255, 255, 255, 0), center_color=(0, 0, 0, 255), edge_color=(0, 0, 255, 255)),
        embeded_image_path=join(getcwd(), "logo.png"),
    )
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    byte_im = buf.getvalue()
    return byte_im
