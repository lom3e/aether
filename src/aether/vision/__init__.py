"""
Screen understanding for the Companion: validation of captured images, per-model vision capability, the analysis
request that goes through the shared runtime/session, and validation of model-suggested annotations.

Capture itself is native (src-tauri/src/screen_capture.rs); rendering is UI (ui/src/companion/vision). This package
holds the portable middle: nothing here reads the screen and nothing here stores an image.
"""
from aether.vision.annotations import Annotation, AnnotationReport, parse_annotations, validate_annotations
from aether.vision.capability import VisionSupport, model_supports_vision, vision_support_for
from aether.vision.image import ImageError, ValidatedImage, validate_image

__all__ = [
    "Annotation", "AnnotationReport", "parse_annotations", "validate_annotations",
    "VisionSupport", "model_supports_vision", "vision_support_for",
    "ImageError", "ValidatedImage", "validate_image",
]
