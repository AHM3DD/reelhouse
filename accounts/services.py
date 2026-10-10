from io import BytesIO

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_AVATAR_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}
ALLOWED_AVATAR_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}
MAX_AVATAR_PIXELS = 25_000_000
AVATAR_SIZE = (400, 400)


def process_avatar(uploaded_file):
    """Validate an uploaded avatar and return a re-encoded 400x400 WebP ContentFile.

    Re-encoding strips metadata (EXIF/GPS) and any non-image payload smuggled in the file.
    """
    max_bytes = settings.AVATAR_MAX_UPLOAD_BYTES
    if uploaded_file.size > max_bytes:
        raise ValidationError(f"Avatar must be {max_bytes // (1024 * 1024)} MB or smaller.")

    extension = uploaded_file.name.rsplit(".", 1)[-1].lower() if "." in uploaded_file.name else ""
    if extension not in ALLOWED_AVATAR_EXTENSIONS:
        raise ValidationError("Upload a JPEG, PNG, WebP or GIF image.")

    try:
        uploaded_file.seek(0)
        with Image.open(uploaded_file) as image:
            if image.format not in ALLOWED_AVATAR_FORMATS:
                raise ValidationError("Upload a JPEG, PNG, WebP or GIF image.")
            if image.width * image.height > MAX_AVATAR_PIXELS:
                raise ValidationError("That image is too large. Please upload a smaller one.")
            image.seek(0)  # first frame of animated images
            image = ImageOps.exif_transpose(image)
            if image.mode in ("RGBA", "LA", "P"):
                image = image.convert("RGBA")
                background = Image.new("RGB", image.size, (17, 17, 24))
                background.paste(image, mask=image.getchannel("A"))
                image = background
            else:
                image = image.convert("RGB")
            image = ImageOps.fit(image, AVATAR_SIZE, Image.Resampling.LANCZOS)
            buffer = BytesIO()
            image.save(buffer, format="WEBP", quality=85, method=4)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValidationError("The file is not a valid image.") from exc
    finally:
        uploaded_file.seek(0)

    return ContentFile(buffer.getvalue(), name="avatar.webp")
