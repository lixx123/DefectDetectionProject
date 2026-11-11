"""Review atlas rendering for descriptive Case03-C candidate features."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


COLORS = {
    "core": np.asarray([255, 220, 40], dtype=np.float32),
    "expanded": np.asarray([40, 220, 255], dtype=np.float32),
    "selected": np.asarray([255, 80, 80], dtype=np.float32),
    "ring": np.asarray([170, 80, 255], dtype=np.float32),
}


def normalize_raw(raw: np.ndarray) -> tuple[np.ndarray, tuple[float, float]]:
    """Create a display-only RAW normalization and return its DN range."""

    low, high = np.percentile(raw, [1.0, 99.5])
    high = max(float(high), float(low) + 1.0)
    display = np.clip((raw.astype(np.float32) - low) / (high - low), 0.0, 1.0)
    return display, (float(low), float(high))


def response_display(response: np.ndarray) -> tuple[np.ndarray, float]:
    """Normalize Black-Hat response for display only; preserve DN elsewhere."""

    high = max(float(np.percentile(response, 99.5)), 1.0)
    return np.clip(response.astype(np.float32) / high, 0.0, 1.0), high


def make_overlay(raw_display: np.ndarray, s_mask: np.ndarray, h_mask: np.ndarray, selected_mask: np.ndarray, ring_mask: np.ndarray | None = None) -> np.ndarray:
    """Render mutually exclusive core/expanded and optional review-ring colors."""

    if not (raw_display.shape == s_mask.shape == h_mask.shape == selected_mask.shape):
        raise ValueError("atlas layers must have identical shapes")
    if np.any(s_mask & ~h_mask):
        raise ValueError("S mask must be contained in H mask")
    image = np.repeat((np.clip(raw_display, 0.0, 1.0) * 255.0)[..., None], 3, axis=2)
    image[s_mask] = image[s_mask] * 0.25 + COLORS["core"] * 0.75
    image[h_mask & ~s_mask] = image[h_mask & ~s_mask] * 0.25 + COLORS["expanded"] * 0.75
    if ring_mask is not None:
        image[ring_mask & ~h_mask] = image[ring_mask & ~h_mask] * 0.35 + COLORS["ring"] * 0.65
    image[selected_mask] = image[selected_mask] * 0.20 + COLORS["selected"] * 0.80
    return np.clip(np.rint(image), 0, 255).astype(np.uint8)


def _panel(ax, image: np.ndarray, title: str, cmap: str | None = None) -> None:
    ax.imshow(image, cmap=cmap, vmin=0 if cmap else None, vmax=1 if cmap else None, interpolation="nearest")
    ax.set_title(title, fontsize=8)
    ax.set_xticks([])
    ax.set_yticks([])


def save_candidate_figure(
    path: Path,
    *,
    title: str,
    raw_display: np.ndarray,
    raw_range: tuple[float, float],
    response_display_image: np.ndarray,
    response_high_dn: float,
    s_mask: np.ndarray,
    h_mask: np.ndarray,
    overlay: np.ndarray,
    ring_mask: np.ndarray,
    selected_mask: np.ndarray,
    feature_note: str,
) -> None:
    """Save a fixed six-panel review image without dense full-image labels."""

    fig, axes = plt.subplots(2, 3, figsize=(12.5, 8.3), dpi=150)
    _panel(axes[0, 0], raw_display, f"RAW display P1={raw_range[0]:.0f}, P99.5={raw_range[1]:.0f} DN", "gray")
    _panel(axes[0, 1], response_display_image, f"Black-Hat response display cap={response_high_dn:.1f} DN", "magma")
    _panel(axes[0, 2], s_mask.astype(np.float32), "S230 exact core", "gray")
    _panel(axes[1, 0], h_mask.astype(np.float32), "H170/230 exact candidate", "gray")
    _panel(axes[1, 1], ring_mask.astype(np.float32), "RAW reference samples actually used", "gray")
    _panel(axes[1, 2], overlay.astype(np.float32) / 255.0, "Yellow core / cyan expansion / purple ring / red selected")
    fig.suptitle(title + "\n" + feature_note + " | candidate_not_truth", fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def save_contact_sheet(path: Path, items: list[dict], title: str, columns: int = 2) -> None:
    """Save a compact page of selected review images grouped by stratum."""

    if not items:
        return
    rows = int(np.ceil(len(items) / columns))
    fig, axes = plt.subplots(rows, columns, figsize=(columns * 5.2, rows * 4.0), dpi=135, squeeze=False)
    for index, item in enumerate(items):
        row, column = divmod(index, columns)
        ax = axes[row, column]
        ax.imshow(item["overlay"], interpolation="nearest")
        ax.set_title(item["title"], fontsize=8)
        ax.set_xticks([])
        ax.set_yticks([])
    for index in range(len(items), rows * columns):
        axes[index // columns, index % columns].axis("off")
    fig.suptitle(title + "\n所有候选均未人工确认为真实疵病", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)

