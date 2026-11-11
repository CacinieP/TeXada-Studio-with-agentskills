"""Portable source-region report assets; original bytes are never interpreted as code.

SVGs reference the content-addressed PNG in the same sources directory. They
are standalone linked previews, not raster crops or automatic annotations.
"""
import hashlib
import json
from pathlib import Path
import re
import struct
import tempfile
import os
import xml.etree.ElementTree as ET

MAX_IMAGE_BYTES = 24 * 1024 * 1024
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
SVG = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG)


def _read_image(path, digest):
    with open(path, "rb") as stream:
        data = stream.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES or hashlib.sha256(data).hexdigest() != digest:
        raise ValueError("source image unavailable or changed")
    return data


def _store(path, data):
    """Repair a changed cached asset with atomic replacement; keep valid bytes."""
    if path.is_file() and not path.is_symlink():
        with path.open("rb") as stream:
            if stream.read(len(data) + 1) == data:
                return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def snapshot(run_dir, sample_path, image):
    """Copy the exact validated image, checking bytes again at snapshot time."""
    digest = image["sha256"]
    if not SHA256.fullmatch(digest):
        raise ValueError("invalid source image digest")
    data = _read_image(Path(sample_path) / "source.png", digest)
    relative = f"sources/{digest}.png"
    _store(Path(run_dir) / relative, data)
    return {"image_path": relative, "image_sha256": digest,
            "width": image["width"], "height": image["height"]}


def node_region(image, node):
    provenance = node["ocr_source"]
    region = provenance["region"]
    text = provenance.get("text")
    text = text if (isinstance(text, list) and len(text) <= 64
                    and all(isinstance(line, str) and len(line) <= 32768 for line in text)) else []
    reviewer = provenance.get("reviewer")
    reviewer = reviewer if isinstance(reviewer, str) and len(reviewer) <= 200 else None
    return {**image, "bbox": list(region["bbox"]),
            "coordinate_system": region["coordinate_system"],
            "annotation_source": region["annotation_source"], "source_text": text,
            "reviewer": reviewer, "page": node.get("page") if type(node.get("page")) is int else None}


def _validated(payload):
    if not isinstance(payload, dict):
        raise ValueError("invalid region evidence")
    digest = payload.get("image_sha256")
    if (not isinstance(digest, str) or not SHA256.fullmatch(digest)
            or payload.get("image_path") != f"sources/{digest}.png"
            or payload.get("annotation_source") != "operator_provided"
            or payload.get("coordinate_system") != "top_left_pixel_xyxy_half_open"
            or any(type(payload.get(key)) is not int or not 1 <= payload[key] <= 32768
                   for key in ("width", "height"))):
        raise ValueError("invalid region source")
    bbox = payload.get("bbox")
    if (not isinstance(bbox, list) or len(bbox) != 4 or any(type(n) is not int for n in bbox)):
        raise ValueError("invalid region bounds")
    x0, y0, x1, y1 = bbox
    if not (0 <= x0 < x1 <= payload["width"] and 0 <= y0 < y1 <= payload["height"]):
        raise ValueError("region outside image")
    return digest


def _svg(payload, *, zoom):
    width, height = payload["width"], payload["height"]
    x0, y0, x1, y1 = payload["bbox"]
    view = (x0, y0, x1 - x0, y1 - y0) if zoom else (0, 0, width, height)
    scale = min(720 / view[2], 720 / view[3])
    display_width = max(1, round(view[2] * scale))
    display_height = max(1, round(view[3] * scale))
    root = ET.Element(f"{{{SVG}}}svg", {"viewBox": " ".join(str(n) for n in view),
                     "width": str(display_width), "height": str(display_height),
                     "role": "img", "aria-label": "Operator-provided OCR source region"})
    ET.SubElement(root, f"{{{SVG}}}title").text = f"Operator-provided region {payload['bbox']}; not content verification"
    ET.SubElement(root, f"{{{SVG}}}image", {"href": payload["image_sha256"] + ".png",
                  "width": str(width), "height": str(height)})
    if not zoom:
        ET.SubElement(root, f"{{{SVG}}}rect", {"x": str(x0), "y": str(y0),
                      "width": str(x1 - x0), "height": str(y1 - y0),
                      "fill": "none", "stroke": "#e63946", "stroke-width": "2",
                      "vector-effect": "non-scaling-stroke"})
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def report_assets(run_dir, payload):
    """Only local, hash-checked PNG paths can appear in report links or SVGs."""
    digest = _validated(payload)
    image = _read_image(Path(run_dir) / payload["image_path"], digest)
    if (len(image) < 24 or image[:16] != b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR"
            or struct.unpack(">II", image[16:24]) != (payload["width"], payload["height"])):
        raise ValueError("source image dimensions do not match journal")
    identity = json.dumps({key: payload[key] for key in ("image_sha256", "width", "height", "bbox")},
                          sort_keys=True, separators=(",", ":")).encode()
    key = hashlib.sha256(identity).hexdigest()
    result = {"image": payload["image_path"]}
    for name, zoom in (("annotated", False), ("zoom", True)):
        relative = f"sources/{key}-{name}.svg"
        _store(Path(run_dir) / relative, _svg(payload, zoom=zoom))
        result[name] = relative
    return result
