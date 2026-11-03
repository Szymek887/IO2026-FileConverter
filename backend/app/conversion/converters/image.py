"""Image converter: jpg / png / heic with Pillow + pillow-heif (no FFmpeg).

Steps: open the primary image (first frame) → apply the EXIF orientation → adapt the pixel
mode to what the target can store → save with the preset quality, carrying over EXIF and,
when the colour space is unchanged, the ICC profile.

Pillow work can't be interrupted, so the `timeout` argument is not used here; images are
limited by `MAX_IMAGE_PIXELS` at upload instead.
"""

import io
import logging
from pathlib import Path

import pillow_heif
from PIL import Image, ImageCms, ImageOps

from app.conversion import probe as media_probe  # also registers the HEIF plugin
from app.conversion.converters import presets
from app.conversion.formats import Format

logger = logging.getLogger(__name__)

pillow_heif.options.GRID_TILE_SIZE = presets.HEIC_GRID_TILE_SIZE  # global pillow-heif option

GRAY_MODES = {"1", "L", "LA", "La", "I", "I;16", "I;16B", "I;16L", "I;16N", "F"}
RGB_MODES = {"RGB", "RGBA", "RGBa", "RGBX", "P", "PA"}
SIXTEEN_BIT_MODES = {"I", "I;16", "I;16B", "I;16L", "I;16N", "F"}
PNG_MODES = {"1", "L", "LA", "I", "I;16", "P", "RGB", "RGBA"}


def convert_image(src: Path, dst: Path, source: Format, target: Format, timeout: int) -> None:
    with Image.open(src, formats=[media_probe.PILLOW_FORMATS[source]]) as opened:
        icc = opened.info.get("icc_profile")
        img = ImageOps.exif_transpose(opened)  # a copy; orientation tag removed
    exif = img.getexif()
    source_family = _color_family(img.mode)

    img = _prepare(img, target, icc)
    if _color_family(img.mode) != source_family:
        icc = None  # a CMYK/gray profile would describe the new pixels wrongly

    options = presets.image_save_options(target)
    if icc:
        options["icc_profile"] = icc
    if exif:
        options["exif"] = exif.tobytes()
    img.save(dst, format=media_probe.PILLOW_FORMATS[target], **options)


def _color_family(mode: str) -> str:
    if mode in GRAY_MODES:
        return "gray"
    if mode in RGB_MODES:
        return "rgb"
    return mode.lower()  # cmyk, ycbcr, lab, ...


def has_alpha(img: Image.Image) -> bool:
    return img.mode in ("RGBA", "RGBa", "LA", "La", "PA") or "transparency" in img.info


def _prepare(img: Image.Image, target: Format, icc: bytes | None) -> Image.Image:
    """Convert `img` to a pixel mode `target` can store, losing as little as possible."""
    if img.mode == "CMYK":
        img = _cmyk_to_rgb(img, icc)
    gray = _color_family(img.mode) == "gray"
    alpha = has_alpha(img)

    if target is Format.PNG:
        if img.mode == "P" and alpha:
            return img.convert("RGBA")
        if img.mode in PNG_MODES:
            return img  # lossless, incl. 16-bit grayscale
        return img.convert(("LA" if alpha else "L") if gray else ("RGBA" if alpha else "RGB"))

    img = _to_8bit(img)
    if target is Format.JPG:
        if alpha:
            img = _flatten(img)
        return img if img.mode in ("L", "RGB") else img.convert("L" if gray else "RGB")

    if target is Format.HEIC:
        wanted = "RGBA" if alpha else "RGB"
        return img if img.mode == wanted else img.convert(wanted)

    raise ValueError(f"{target} is not an image format")


def _to_8bit(img: Image.Image) -> Image.Image:
    """Scale 16-bit/float grayscale to 8-bit (a plain convert would clip it to white)."""
    if img.mode not in SIXTEEN_BIT_MODES:
        return img
    if img.mode == "F":
        return img.convert("L")
    return img.convert("I").point(lambda value: value * (1 / 256)).convert("L")


def _flatten(img: Image.Image) -> Image.Image:
    """Composite onto `FLATTEN_BACKGROUND`; grayscale stays grayscale."""
    gray = _color_family(img.mode) == "gray"
    rgba = img.convert("RGBA")
    background = Image.new("RGBA", rgba.size, (*presets.FLATTEN_BACKGROUND, 255))
    flat = Image.alpha_composite(background, rgba).convert("RGB")
    return flat.convert("L") if gray else flat


def _cmyk_to_rgb(img: Image.Image, icc: bytes | None) -> Image.Image:
    """Colour-managed CMYK -> sRGB using the embedded profile, plain conversion otherwise."""
    if icc:
        try:
            converted = ImageCms.profileToProfile(
                img,
                ImageCms.ImageCmsProfile(io.BytesIO(icc)),
                ImageCms.createProfile("sRGB"),
                outputMode="RGB",
            )
            if converted is not None:
                return converted
        except (ImageCms.PyCMSError, OSError) as exc:
            logger.info("CMYK profile conversion failed, converting without it: %s", exc)
    return img.convert("RGB")
