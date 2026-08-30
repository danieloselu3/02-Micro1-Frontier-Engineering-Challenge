"""Render pre-authorization forms, then damage them on purpose.

A clean digital PDF is not what arrives at a payer. Real prior-auth requests
come off a fax at 200 DPI with speckle, or as a phone photograph taken at an
angle under office lighting, or with the member id filled in by hand. Those
are the documents extraction has to survive, so the generator produces them.

Every transformation is seeded from the case id, so a given case always
degrades identically. Without that, extraction accuracy would drift between
runs and the per-tier comparison would be meaningless.
"""

from __future__ import annotations

import io
import random
import zlib
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from data.generator.reference import DIAGNOSES_BY_CODE, PROCEDURES_BY_CODE
from packages.core.labels import GeneratedCase
from packages.core.models import DegradationTier

PAGE_W, PAGE_H = LETTER
RENDER_DPI = 150


# --------------------------------------------------------------------------
# Render
# --------------------------------------------------------------------------


def render_pdf(case: GeneratedCase) -> tuple[bytes, dict[str, tuple[float, float]]]:
    """Draw the form as a clean vector PDF.

    Returns the bytes and a map of field name to the baseline position it was
    drawn at, in PDF points. The handwriting overlay needs to land exactly on
    the printed member id, and recomputing the layout arithmetic separately is
    how it ends up floating at the bottom of the page instead.
    """
    anchors: dict[str, tuple[float, float]] = {}
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    proc = PROCEDURES_BY_CODE[case.procedure_code]

    left = 0.75 * inch
    right = PAGE_W - 0.75 * inch
    y = PAGE_H - 0.7 * inch

    # -- masthead ----------------------------------------------------------
    c.setFont("Helvetica-Bold", 15)
    c.drawString(left, y, "MERIDIAN HEALTH PLAN")
    c.setFont("Helvetica", 8.5)
    c.drawRightString(right, y + 2, "Form UM-101 (Rev. 01/2026)")
    y -= 15
    c.setFont("Helvetica-Bold", 11.5)
    c.drawString(left, y, "PRIOR AUTHORIZATION REQUEST")
    y -= 8
    c.setLineWidth(1.2)
    c.line(left, y, right, y)
    y -= 6
    c.setFont("Helvetica-Oblique", 7.5)
    c.drawString(
        left,
        y,
        "Incomplete forms will be returned. Fax to (614) 555-0189 or submit via "
        "the provider portal.",
    )
    y -= 20

    def section(title: str, ypos: float) -> float:
        c.setFillGray(0.9)
        c.rect(left, ypos - 3, right - left, 14, stroke=0, fill=1)
        c.setFillGray(0)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(left + 4, ypos + 1, title)
        return ypos - 20

    def field(label: str, value: str, x: float, ypos: float, width: float) -> None:
        anchors[label] = (x, ypos)
        c.setFont("Helvetica", 7.5)
        c.setFillGray(0.35)
        c.drawString(x, ypos + 11, label.upper())
        c.setFillGray(0)
        c.setFont("Helvetica", 10)
        c.drawString(x + 1, ypos, value)
        c.setLineWidth(0.5)
        c.setStrokeGray(0.6)
        c.line(x, ypos - 3, x + width, ypos - 3)
        c.setStrokeGray(0)

    col2 = left + 3.5 * inch
    half = 3.1 * inch

    # -- member ------------------------------------------------------------
    y = section("SECTION A - MEMBER INFORMATION", y)
    field("Member Name", case.form_member_name, left, y, half)
    field("Member ID", case.form_member_id, col2, y, half)
    y -= 34
    field("Date of Birth", case.member.date_of_birth.strftime("%m/%d/%Y"), left, y, half)
    field("Group Number", case.member.group_id, col2, y, half)
    y -= 34
    field("Plan", case.member.plan_id, left, y, half)
    field("State of Residence", case.member.state, col2, y, half)
    y -= 30

    # -- provider ----------------------------------------------------------
    y = section("SECTION B - REQUESTING PROVIDER", y)
    field("Provider / Facility Name", case.provider.name, left, y, half)
    field("NPI", case.form_provider_npi, col2, y, half)
    y -= 34
    field("Specialty", case.provider.specialty, left, y, half)
    field("License State", case.provider.license_state, col2, y, half)
    y -= 30

    # -- service -----------------------------------------------------------
    y = section("SECTION C - REQUESTED SERVICE", y)
    field("Procedure Code (CPT/HCPCS)", case.procedure_code, left, y, half)
    field("Date of Service", case.form_date_of_service, col2, y, half)
    y -= 34
    field("Procedure Description", proc.description[:48], left, y, half)
    field("Units Requested", str(case.units_requested), col2, y, half)
    y -= 34
    dx = case.diagnosis_codes[0] if case.diagnosis_codes else ""
    dx_desc = DIAGNOSES_BY_CODE[dx].description if dx in DIAGNOSES_BY_CODE else ""
    field("Diagnosis Code (ICD-10)", dx, left, y, half)
    field("Diagnosis Description", dx_desc[:46], col2, y, half)
    y -= 30

    # -- narrative ---------------------------------------------------------
    y = section("SECTION D - CLINICAL JUSTIFICATION", y)
    c.setFont("Helvetica", 8.6)
    for para in case.clinical_narrative.strip().split("\n\n"):
        for line in _wrap(para.replace("\n", " "), 104):
            if y < 1.0 * inch:
                c.showPage()
                y = PAGE_H - 0.8 * inch
                c.setFont("Helvetica", 8.6)
            c.drawString(left, y, line)
            y -= 10.6
        y -= 5

    # -- attestation -------------------------------------------------------
    y = max(y - 10, 0.8 * inch)
    c.setLineWidth(0.5)
    c.line(left, y + 12, right, y + 12)
    c.setFont("Helvetica-Oblique", 7.2)
    c.drawString(
        left,
        y,
        "I certify that the information above is accurate and that the requested service is "
        "medically necessary for this member.",
    )
    c.setFont("Helvetica", 8)
    c.drawString(left, y - 22, f"Signature: {case.provider.name}")
    c.drawString(col2, y - 22, f"Date: {case.form_date_of_service}")

    c.save()
    return buf.getvalue(), anchors


def _wrap(text: str, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines


# --------------------------------------------------------------------------
# Degrade
# --------------------------------------------------------------------------


def pdf_to_image(pdf_bytes: bytes, dpi: int = RENDER_DPI) -> Image.Image:
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(pdf_bytes)
    page = doc[0]
    pil = page.render(scale=dpi / 72).to_pil().convert("L")
    doc.close()
    return pil


def degrade(img: Image.Image, tier: DegradationTier, seed: int) -> Image.Image:
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)

    if tier == DegradationTier.CLEAN:
        return img

    if tier == DegradationTier.SCAN:
        # A sheet fed slightly crooked, with the mild blur of a flatbed.
        img = img.rotate(rng.uniform(-1.6, 1.6), expand=True, fillcolor=255,
                         resample=Image.BICUBIC)
        img = img.filter(ImageFilter.GaussianBlur(0.45))
        return _add_noise(img, np_rng, sigma=4)

    if tier == DegradationTier.FAX:
        # 200 DPI, hard contrast, speckle, and the horizontal streaking a
        # thermal fax leaves behind.
        w, h = img.size
        img = img.resize((int(w * 0.55), int(h * 0.55)), Image.BILINEAR)
        img = img.rotate(rng.uniform(-0.9, 0.9), expand=True, fillcolor=255,
                         resample=Image.BICUBIC)
        img = ImageEnhance.Contrast(img).enhance(2.1)
        img = _add_noise(img, np_rng, sigma=13)
        img = _streak(img, np_rng, n=rng.randint(3, 7))
        return img.point(lambda p: 0 if p < 118 else 255).resize(
            (int(w * 0.8), int(h * 0.8)), Image.NEAREST
        )

    if tier == DegradationTier.PHOTO:
        # Handheld, off-axis, with a soft shadow gradient across the page.
        img = img.rotate(rng.uniform(-3.2, 3.2), expand=True, fillcolor=245,
                         resample=Image.BICUBIC)
        img = _shadow(img, rng)
        img = ImageEnhance.Brightness(img).enhance(rng.uniform(0.82, 0.96))
        img = img.filter(ImageFilter.GaussianBlur(0.75))
        return _add_noise(img, np_rng, sigma=7)

    if tier == DegradationTier.HANDWRITTEN:
        # Scan quality, plus the member id overwritten by hand with one
        # character deliberately malformed.
        img = img.rotate(rng.uniform(-1.2, 1.2), expand=True, fillcolor=255,
                         resample=Image.BICUBIC)
        img = _add_noise(img, np_rng, sigma=5)
        return img.filter(ImageFilter.GaussianBlur(0.4))

    return img


def _add_noise(img: Image.Image, rng: np.random.Generator, sigma: float) -> Image.Image:
    arr = np.asarray(img).astype(np.int16)
    arr = arr + rng.normal(0, sigma, arr.shape).astype(np.int16)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), mode="L")


def _streak(img: Image.Image, rng: np.random.Generator, n: int) -> Image.Image:
    arr = np.asarray(img).copy()
    h = arr.shape[0]
    for _ in range(n):
        row = int(rng.integers(0, h))
        thickness = int(rng.integers(1, 3))
        arr[row : row + thickness, :] = int(rng.integers(180, 255))
    return Image.fromarray(arr, mode="L")


def _shadow(img: Image.Image, rng: random.Random) -> Image.Image:
    """A soft linear falloff, as if the page were lit from one side."""
    w, h = img.size
    grad = np.linspace(rng.uniform(0.72, 0.88), 1.0, w, dtype=np.float32)
    if rng.random() < 0.5:
        grad = grad[::-1]
    mask = np.tile(grad, (h, 1))
    arr = np.asarray(img).astype(np.float32) * mask
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), mode="L")


def handwrite_member_id(
    img: Image.Image,
    member_id: str,
    anchor: tuple[float, float],
    seed: int,
    dpi: int = RENDER_DPI,
) -> Image.Image:
    """White out the printed member id and fill it in by hand instead.

    One character in the numeric tail is rendered ambiguously on purpose. The
    correct behaviour downstream is to resolve identity on the name and date
    of birth rather than guess the digit, so this case tests judgment rather
    than raw OCR accuracy.

    `anchor` is the PDF-point baseline reported by render_pdf. PDF space has
    its origin bottom-left and PIL top-left, hence the flip.
    """
    rng = random.Random(seed)
    draw = ImageDraw.Draw(img)
    scale = dpi / 72.0

    px = anchor[0] * scale
    # Flip the y axis, then lift the box to sit above the baseline.
    baseline = (PAGE_H - anchor[1]) * scale
    top = baseline - 15 * scale / 2.08

    box_w = 2.4 * inch * scale
    draw.rectangle([px - 4, top - 4, px + box_w, baseline + 4], fill=255)

    font = _handwriting_font(size=int(20 * scale / 2.08))
    cx = px
    tail_start = len(member_id) - 3
    for i, ch in enumerate(member_id):
        jitter = rng.randint(-2, 2)
        if i == tail_start:
            # The illegible one: faint, and overwritten with a correction loop.
            draw.text((cx, top + jitter), ch, fill=125, font=font)
            draw.ellipse(
                [cx - 2, top + jitter + 3, cx + 14, top + jitter + 19], outline=155
            )
        else:
            draw.text((cx, top + jitter), ch, fill=30, font=font)
        cx += 14 if ch != "-" else 9
    return img


def _handwriting_font(size: int) -> ImageFont.ImageFont:
    for name in ("segoesc.ttf", "comic.ttf", "Segoe Script", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def build_document(case: GeneratedCase, out_dir: Path) -> Path:
    """Render, degrade, and write the document this case arrives as.

    Clean cases stay PDFs, because that is genuinely how a portal submission
    arrives. Everything else becomes a PNG, because that is what a fax
    gateway or a phone produces.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf, anchors = render_pdf(case)
    tier = case.label.degradation
    # crc32, not hash(): Python randomises string hashing per process unless
    # PYTHONHASHSEED is pinned, which would make degradation differ between
    # runs and silently invalidate the per-tier extraction comparison.
    seed = zlib.crc32(case.case_id.encode())

    if tier == DegradationTier.CLEAN:
        path = out_dir / f"{case.case_id}.pdf"
        path.write_bytes(pdf)
        return path

    img = pdf_to_image(pdf)
    if tier == DegradationTier.HANDWRITTEN:
        img = handwrite_member_id(img, case.form_member_id, anchors["Member ID"], seed)
    img = degrade(img, tier, seed)

    path = out_dir / f"{case.case_id}.png"
    img.save(path, format="PNG", optimize=True)
    return path
