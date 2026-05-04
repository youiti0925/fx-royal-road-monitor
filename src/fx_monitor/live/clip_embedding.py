"""CLIP-based visual embedding for chart images.

Pure CPU-friendly. The model is loaded lazily and cached at module
level so subsequent embeds are fast (~50-200ms on CPU). Returns a
512-dimensional ``np.ndarray`` (ViT-B/32 output dimension).

Visual embedding captures chart **shape** in a way the 272-dim numeric
vector cannot — pattern gestalt (double top, ascending triangle, etc.)
that a vision transformer learned from natural images.

Designed to be optional: if open_clip / torch are not installed, the
module raises ``RuntimeError`` only when an embed is actually
requested. The rest of the package stays importable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np


_MODEL_NAME = "ViT-B-32"
_PRETRAINED_TAG = "laion2b_s34b_b79k"
_EMBED_DIM = 512

_state: dict[str, Any] = {"model": None, "preprocess": None, "device": None}


def _ensure_model() -> tuple[Any, Any, str]:
    """Load the CLIP model and image preprocessor lazily.

    Cached after first call. CPU-only by default; CUDA is used when
    available. Raises :class:`RuntimeError` with a helpful hint if
    open_clip / torch is not installed.
    """
    if _state["model"] is not None:
        return _state["model"], _state["preprocess"], _state["device"]

    try:
        import open_clip  # type: ignore
        import torch  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "CLIP embedding requires open_clip_torch + torch. "
            "Install with: pip install open_clip_torch torch"
        ) from e

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model, _, preprocess = open_clip.create_model_and_transforms(
        _MODEL_NAME, pretrained=_PRETRAINED_TAG
    )
    model = model.to(device).eval()
    _state["model"] = model
    _state["preprocess"] = preprocess
    _state["device"] = device
    return model, preprocess, device


def embed_image(image_path: Path | str) -> np.ndarray:
    """Return the 512-dim CLIP embedding for ``image_path``.

    The vector is L2-normalised so cosine similarity becomes a simple
    dot product.
    """
    p = Path(image_path)
    if not p.exists():
        raise FileNotFoundError(p)

    from PIL import Image  # type: ignore
    import torch  # type: ignore

    model, preprocess, device = _ensure_model()
    img = Image.open(p).convert("RGB")
    tensor = preprocess(img).unsqueeze(0).to(device)
    with torch.no_grad():
        feats = model.encode_image(tensor)
        feats = feats / feats.norm(dim=-1, keepdim=True)
    vec = feats.squeeze(0).cpu().numpy().astype(np.float64)
    return vec


def is_available() -> bool:
    """Return True if open_clip + torch are installed.

    Safe to call without side effects; does not load the model.
    """
    try:
        import open_clip  # noqa: F401
        import torch  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        return False
    return True


__all__ = ["embed_image", "is_available", "_EMBED_DIM"]
