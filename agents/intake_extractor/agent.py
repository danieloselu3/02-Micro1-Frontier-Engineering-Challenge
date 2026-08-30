"""Intake: read the form, and report honestly on what could not be read.

Two properties this stage owes the rest of the pipeline:

* Every value carries a confidence and, where possible, the region of the
  page it came from. Without provenance the reviewer console can only show
  a nurse a list of assertions to take on faith, which is not review.

* An unreadable character is reported as unreadable. Guessing a digit in a
  member id can land on a real and entirely different member, and silently
  adjudicate the wrong person's benefits. Downstream resolution can recover
  identity from name and date of birth; it cannot recover from a confident
  wrong answer.

Fields that come back below the re-read threshold get a second, targeted
look at a higher resolution before the pipeline moves on.
"""

from __future__ import annotations

import base64
import io
from pathlib import Path

from PIL import Image

from agents.client import ModelClient, extract_json
from packages.core.config import EXTRACTION_MODEL, FIELD_REREAD_THRESHOLD
from packages.core.models import BoundingBox, ExtractedField, ExtractedRequest
from packages.observability.ledger import CostLedger

PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")

STAGE = "extract"
STAGE_REREAD = "extract_reread"

#: Scored against the gold labels. Other fields are extracted for the
#: reviewer's benefit but are not part of the accuracy figure.
CRITICAL_FIELDS = (
    "member_name",
    "member_id",
    "provider_npi",
    "procedure_code",
    "diagnosis_code",
    "date_of_service",
)

ALL_FIELDS = CRITICAL_FIELDS + (
    "date_of_birth",
    "group_number",
    "plan",
    "provider_name",
    "license_state",
    "units_requested",
)


def extract(
    *,
    client: ModelClient,
    ledger: CostLedger,
    document_path: Path,
    submission_id: str,
    model: str = EXTRACTION_MODEL,
    reread: bool = True,
) -> ExtractedRequest:
    image = load_page(document_path)
    payload = _image_block(image)

    raw = client.complete(
        stage=STAGE,
        model=model,
        system=PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    payload,
                    {
                        "type": "text",
                        "text": (
                            "Transcribe this prior-authorization form. Return "
                            "the JSON object described in your instructions "
                            "and nothing else."
                        ),
                    },
                ],
            }
        ],
        ledger=ledger,
        max_tokens=8000,
    )

    request = _parse(raw, submission_id)

    if reread:
        weak = request.low_confidence(FIELD_REREAD_THRESHOLD)
        if weak:
            request = _reread(
                client=client,
                ledger=ledger,
                image=image,
                request=request,
                fields=weak,
                model=model,
            )
    return request


# --------------------------------------------------------------------------
# Targeted second pass
# --------------------------------------------------------------------------


def _reread(
    *,
    client: ModelClient,
    ledger: CostLedger,
    image: Image.Image,
    request: ExtractedRequest,
    fields: list[str],
    model: str,
) -> ExtractedRequest:
    """Look again at just the fields that came back uncertain.

    The whole page is sent again at higher resolution rather than a crop:
    cropping to a bounding box the first pass produced would inherit that
    pass's mistake about where the field is, and a field it located wrongly
    is exactly the field most likely to be wrong.
    """
    upscaled = image.resize(
        (int(image.width * 1.6), int(image.height * 1.6)), Image.LANCZOS
    )
    listing = "\n".join(f"- {name}" for name in sorted(fields))

    raw = client.complete(
        stage=STAGE_REREAD,
        model=model,
        system=PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    _image_block(upscaled),
                    {
                        "type": "text",
                        "text": (
                            "A first pass over this form returned low "
                            "confidence for the following fields:\n\n"
                            f"{listing}\n\n"
                            "This image is enlarged. Read those fields again "
                            "carefully. Return the same JSON structure, but "
                            "include only the fields listed above. If a "
                            "character is still unreadable, keep the '?' and "
                            "the low confidence -- do not guess it."
                        ),
                    },
                ],
            }
        ],
        ledger=ledger,
        max_tokens=4000,
    )

    try:
        data = extract_json(raw)
    except ValueError:
        return request

    updated = dict(request.fields)
    for name, payload in data.get("fields", {}).items():
        if name not in fields or not isinstance(payload, dict):
            continue
        candidate = _field(name, payload, reread=True)
        previous = updated.get(name)
        # Keep the second reading only when it is genuinely more certain.
        if previous is None or candidate.confidence > previous.confidence:
            updated[name] = candidate

    return request.model_copy(
        update={"fields": updated, "overall_confidence": _overall(updated)}
    )


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------


def _parse(raw: str, submission_id: str) -> ExtractedRequest:
    """Turn the response into a typed request.

    An unusable response -- empty, or not JSON -- yields an empty request
    rather than an exception. That is not defensiveness for its own sake: an
    empty extraction resolves to no member, which makes the rules return
    UNKNOWN, which pends the case for a human. A document the system could
    not read is exactly a case a person should look at, so the existing
    precedence already handles it correctly and no special path is needed.

    Raising instead would lose the submission entirely, which is the one
    outcome a payer cannot have.
    """
    try:
        data = extract_json(raw)
    except ValueError:
        return ExtractedRequest(
            submission_id=submission_id,
            fields={
                name: ExtractedField(name=name, value=None, confidence=0.0)
                for name in ALL_FIELDS
            },
            clinical_narrative="",
            overall_confidence=0.0,
        )

    payload = data.get("fields", {})

    fields: dict[str, ExtractedField] = {}
    for name in ALL_FIELDS:
        item = payload.get(name)
        fields[name] = (
            _field(name, item)
            if isinstance(item, dict)
            else ExtractedField(name=name, value=None, confidence=0.0)
        )

    return ExtractedRequest(
        submission_id=submission_id,
        fields=fields,
        clinical_narrative=str(data.get("clinical_narrative") or "").strip(),
        overall_confidence=_overall(fields),
    )


def _field(name: str, payload: dict, reread: bool = False) -> ExtractedField:
    value = payload.get("value")
    text = str(value).strip() if value not in (None, "") else None

    confidence = _clamp(payload.get("confidence", 0.0))
    # A value the model flagged as partly unreadable cannot be high
    # confidence, whatever number it attached to it.
    if text and "?" in text:
        confidence = min(confidence, 0.4)
    if text is None:
        confidence = 0.0

    return ExtractedField(
        name=name,
        value=text,
        confidence=confidence,
        source=_bbox(payload.get("bbox")),
        reread=reread,
    )


def _bbox(raw) -> BoundingBox | None:
    if not isinstance(raw, dict):
        return None
    try:
        return BoundingBox(
            page=int(raw.get("page", 0)),
            x=_clamp(raw["x"]),
            y=_clamp(raw["y"]),
            width=_clamp(raw["width"]),
            height=_clamp(raw["height"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _overall(fields: dict[str, ExtractedField]) -> float:
    """Averaged over the critical fields only.

    Including the incidental ones would let a crisply-printed group number
    mask an illegible member id, which is the opposite of what this number
    is for.
    """
    scores = [fields[f].confidence for f in CRITICAL_FIELDS if f in fields]
    return round(sum(scores) / len(scores), 4) if scores else 0.0


def _clamp(value) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


# --------------------------------------------------------------------------
# Document loading
# --------------------------------------------------------------------------


def load_page(path: Path, max_edge: int = 1800) -> Image.Image:
    """Load page one of a document as an image.

    PDFs and images take the same path from here on, so the pipeline has one
    code path regardless of whether the request arrived through the portal
    or off a fax.
    """
    if path.suffix.lower() == ".pdf":
        from data.generator.forms import pdf_to_image

        image = pdf_to_image(path.read_bytes())
    else:
        image = Image.open(path)

    image = image.convert("L")
    if max(image.size) > max_edge:
        scale = max_edge / max(image.size)
        image = image.resize(
            (int(image.width * scale), int(image.height * scale)), Image.LANCZOS
        )
    return image


def _image_block(image: Image.Image) -> dict:
    buf = io.BytesIO()
    image.save(buf, format="PNG", optimize=True)
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": base64.b64encode(buf.getvalue()).decode("ascii"),
        },
    }
