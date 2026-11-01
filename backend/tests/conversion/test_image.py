"""Image converter (jpg / png / heic). Pillow + pillow-heif only – no FFmpeg needed."""

import pytest
from PIL import Image, ImageCms

from app.conversion.converters import CONVERTERS, convert, presets
from app.conversion.converters.image import _cmyk_to_rgb
from app.conversion.formats import Category, Format, allowed_targets
from app.conversion.probe import probe

ORIENTATION = 0x0112
MAKE = 0x010F
SRGB = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def run(src, source: Format, target: Format, tmp_path) -> Image.Image:
    dst = tmp_path / f"out.{target}"
    convert(src, dst, source, target, 60)
    probe(dst, target)  # valid file of the target format
    img = Image.open(dst)
    img.load()
    return img


def close(actual, expected, tolerance=4) -> bool:
    actual = actual if isinstance(actual, tuple) else (actual,)
    expected = expected if isinstance(expected, tuple) else (expected,)
    return all(abs(a - e) <= tolerance for a, e in zip(actual, expected, strict=True))


def test_image_converter_is_registered():
    assert CONVERTERS[Category.IMAGE].__name__ == "convert_image"


def test_presets():
    assert presets.image_save_options(Format.JPG) == {
        "quality": 95,
        "subsampling": 0,
        "optimize": True,
    }
    assert presets.image_save_options(Format.HEIC) == {"quality": 90}
    with pytest.raises(ValueError):
        presets.image_save_options(Format.MP3)


@pytest.mark.parametrize(
    ("name", "source"),
    [("alpha.png", Format.PNG), ("photo.jpg", Format.JPG), ("photo.heic", Format.HEIC)],
)
def test_all_pairs(media, tmp_path, name, source):
    for target in allowed_targets(source):
        img = run(media / name, source, target, tmp_path)
        assert img.size == (40, 30), (source, target)


# --- transparency ----------------------------------------------------------------------


def test_png_alpha_is_flattened_onto_white_for_jpg(media, tmp_path):
    img = run(media / "alpha.png", Format.PNG, Format.JPG, tmp_path)  # (255, 0, 0, 128)
    assert img.mode == "RGB"
    assert close(img.getpixel((20, 15)), (255, 127, 127))


def test_png_alpha_is_kept_for_heic(media, tmp_path):
    img = run(media / "alpha.png", Format.PNG, Format.HEIC, tmp_path)
    assert img.mode == "RGBA"
    assert close(img.getpixel((20, 15))[3], 128)


@pytest.fixture
def palette_png(tmp_path):
    """Left half: palette index 0 marked transparent (blue); right half: opaque red."""
    img = Image.new("P", (20, 10), 0)
    img.putpalette([0, 0, 255, 255, 0, 0] + [0] * 762)
    img.paste(1, (10, 0, 20, 10))
    path = tmp_path / "palette.png"
    img.save(path, transparency=0)
    return path


def test_palette_transparency(palette_png, tmp_path):
    jpg = run(palette_png, Format.PNG, Format.JPG, tmp_path)
    assert close(jpg.getpixel((2, 5)), (255, 255, 255))
    assert close(jpg.getpixel((17, 5)), (255, 0, 0))

    heic = run(palette_png, Format.PNG, Format.HEIC, tmp_path)
    assert heic.mode == "RGBA"
    assert heic.getpixel((2, 5))[3] < 10
    assert heic.getpixel((17, 5))[3] > 245


def test_gray_with_alpha_stays_gray_in_jpg(tmp_path):
    src = tmp_path / "la.png"
    Image.new("LA", (10, 10), (0, 0)).save(src)  # fully transparent black
    img = run(src, Format.PNG, Format.JPG, tmp_path)
    assert img.mode == "L"
    assert close(img.getpixel((5, 5)), 255)


# --- orientation, metadata, colour -----------------------------------------------------


@pytest.fixture
def rotated_jpg(tmp_path):
    """Stored 40x30 (left half red, right half blue), EXIF says rotate 90° clockwise."""
    img = Image.new("RGB", (40, 30), "blue")
    img.paste((255, 0, 0), (0, 0, 20, 30))
    exif = Image.Exif()
    exif[ORIENTATION] = 6
    exif[MAKE] = "TestCam"
    path = tmp_path / "rotated.jpg"
    img.save(path, quality=95, exif=exif.tobytes())
    return path


@pytest.mark.parametrize("target", [Format.PNG, Format.HEIC])
def test_exif_orientation_is_applied(rotated_jpg, tmp_path, target):
    img = run(rotated_jpg, Format.JPG, target, tmp_path)
    assert img.size == (30, 40)
    assert close(img.convert("RGB").getpixel((15, 5)), (255, 0, 0), tolerance=30)  # top: red
    assert close(img.convert("RGB").getpixel((15, 35)), (0, 0, 255), tolerance=30)
    exif = img.getexif()
    assert exif.get(ORIENTATION, 1) == 1  # not rotated a second time by viewers
    assert exif.get(MAKE) == "TestCam"  # other EXIF kept


def test_exif_is_kept_from_heic(tmp_path):
    exif = Image.Exif()
    exif[MAKE] = "iPhone"
    src = tmp_path / "in.heic"
    Image.new("RGB", (8, 8), "green").save(src, quality=90, exif=exif.tobytes())
    assert run(src, Format.HEIC, Format.JPG, tmp_path).getexif().get(MAKE) == "iPhone"


@pytest.mark.parametrize(
    ("source", "target"), [(Format.PNG, Format.JPG), (Format.PNG, Format.HEIC)]
)
def test_icc_profile_is_kept(tmp_path, source, target):
    src = tmp_path / f"in.{source}"
    Image.new("RGB", (8, 8), "orange").save(src, icc_profile=SRGB)
    assert run(src, source, target, tmp_path).info.get("icc_profile") == SRGB


def test_cmyk_jpg_becomes_rgb_png(tmp_path):
    src = tmp_path / "cmyk.jpg"
    Image.new("CMYK", (10, 10), (0, 255, 255, 0)).save(src, quality=95)  # red
    img = run(src, Format.JPG, Format.PNG, tmp_path)
    assert img.mode == "RGB"
    assert close(img.getpixel((5, 5)), (255, 0, 0), tolerance=10)
    assert "icc_profile" not in img.info


def test_cmyk_with_broken_profile_falls_back():
    img = _cmyk_to_rgb(Image.new("CMYK", (2, 2), (0, 0, 0, 0)), b"not a profile")
    assert img.mode == "RGB"


def test_large_heic_is_tiled_and_decodable(tmp_path):
    import pillow_heif

    assert pillow_heif.options.GRID_TILE_SIZE == presets.HEIC_GRID_TILE_SIZE
    src = tmp_path / "wide.png"
    width = presets.HEIC_GRID_TILE_SIZE + 100  # 2 tiles wide
    Image.effect_noise((width, 64), 40).convert("RGB").save(src)
    assert run(src, Format.PNG, Format.HEIC, tmp_path).size == (width, 64)


# --- bit depth -------------------------------------------------------------------------


@pytest.fixture
def gray16_png(tmp_path):
    """Four 8-px stripes with 16-bit values 0, 256, 32768, 65535."""
    img = Image.new("I;16", (32, 8))
    for x in range(32):  # paste() with an int doesn't store 16-bit values correctly
        for y in range(8):
            img.putpixel((x, y), (0, 256, 32768, 65535)[x // 8])
    assert [img.getpixel((x, 0)) for x in (4, 12, 20, 28)] == [0, 256, 32768, 65535]
    path = tmp_path / "gray16.png"
    img.save(path)
    return path


def test_16_bit_png_is_scaled_not_clipped_for_jpg(gray16_png, tmp_path):
    img = run(gray16_png, Format.PNG, Format.JPG, tmp_path)
    assert img.mode == "L"
    for i, expected in enumerate((0, 1, 128, 255)):
        assert close(img.getpixel((i * 8 + 4, 4)), expected), i


def test_16_bit_png_to_heic(gray16_png, tmp_path):
    img = run(gray16_png, Format.PNG, Format.HEIC, tmp_path)
    assert close(img.getpixel((20, 4))[0], 128, tolerance=6)


def test_gray_jpg_stays_gray_in_png(tmp_path):
    src = tmp_path / "gray.jpg"
    Image.new("L", (8, 8), 100).save(src, quality=95)
    img = run(src, Format.JPG, Format.PNG, tmp_path)
    assert img.mode == "L"
    assert close(img.getpixel((4, 4)), 100)


# --- through the worker ----------------------------------------------------------------


def test_image_job_end_to_end(auth_client, db, media):
    from app.conversion import storage
    from app.conversion.models import Job, JobStatus
    from app.conversion.worker import process_job

    response = auth_client.post(
        "/api/jobs",
        files=[
            ("files", ("zdjęcie.png", (media / "alpha.png").read_bytes())),
            ("files", ("IMG_0001.HEIC", (media / "photo.heic").read_bytes())),
        ],
        data={"target_format": "jpg"},
    )
    assert response.status_code == 202, response.text
    job_id = response.json()["id"]

    process_job(job_id)

    job = db.get(Job, job_id)
    assert job.status is JobStatus.DONE, job.result.message
    assert [o.name for o in job.result.outputs] == ["zdjęcie.jpg", "IMG_0001.jpg"]
    for out in job.result.outputs:
        assert probe(storage.to_absolute(out.path), Format.JPG).image.mode == "RGB"
