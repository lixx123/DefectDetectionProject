"""Case03-F: local RAW contrast trial on saved Case03-E2-H 9-window H masks.
Writes only to a new outputs/case03f_localcontrast/<run-id> directory.
Never updates H masks, H-seeded refinement, user labels or source ROI files.
"""
from __future__ import annotations
import argparse
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from config import user_config as cfg
from src.detection.candidate_local_noise import (
    NoiseTrialConfig, classify_candidate, local_raw_statistics,
)

LOG = logging.getLogger(__name__)
SOURCE = ROOT / "outputs/case03e2/run_20261010_H_seeded_bounded_consensus_v5"


def gray_rgb(raw: np.ndarray) -> np.ndarray:
    """RAW only transformed to 8-bit for visualization (not statistics)."""
    v = raw.astype(np.float32)
    low, high = np.percentile(v, [1.0, 99.5])
    high = max(float(high), float(low) + 1.0)
    return cv2.cvtColor(
        np.uint8(np.round(np.clip((v - low) / (high - low), 0, 1) * 255)),
        cv2.COLOR_GRAY2BGR)


def overlay(raw: np.ndarray, colored: np.ndarray, title: str,
            color: tuple[int, int, int]) -> np.ndarray:
    im = gray_rgb(raw)
    im[colored] = np.uint8(0.35 * im[colored] + 0.65 * np.array(color))
    panel = cv2.copyMakeBorder(im, 26, 0, 0, 0, cv2.BORDER_CONSTANT, value=(35, 35, 35))
    cv2.putText(panel, title, (6, 18), cv2.FONT_HERSHEY_SIMPLEX, .43,
                (240, 240, 240), 1, cv2.LINE_AA)
    return panel


def run(source: Path, run_id: str, params: NoiseTrialConfig) -> Path:
    if not source.is_dir():
        raise FileNotFoundError(source)
    output = cfg.OUTPUT_ROOT / "case03f_localcontrast" / run_id
    if output.exists():
        raise FileExistsError(f"refusing to overwrite experiment output: {output}")
    output.mkdir(parents=True)
    figures = output / "figures"
    figures.mkdir()
    original = pd.read_csv(source / "all_original_H_components_in_windows.csv",
                           encoding="utf-8-sig")
    raw = np.memmap(cfg.DATA_ROOT / "26 (1).raw", mode="r", dtype=">u2",
                    shape=(cfg.RAW_HEIGHT, cfg.RAW_WIDTH))
    records, summaries = [], []
    for p in sorted((source / "masks").glob("E2_W*_labels.npz")):
        win = p.name.split("_labels")[0]
        with np.load(p) as z:
            H = z["H170_230"].astype(bool)
            origin_x, origin_y = (int(v) for v in z["roi_origin_raw_xy"])
        ysize, xsize = H.shape
        tile = np.asarray(raw[origin_y:origin_y+ysize, origin_x:origin_x+xsize],
                          dtype=np.uint16)
        n, labels, stats, _ = cv2.connectedComponentsWithStats(
            H.astype(np.uint8), connectivity=8)
        expected = original.loc[original.window_id == win].set_index("local_H_id")
        if len(expected) != n-1:
            raise AssertionError(f"{win}: original H count changed")
        large_ids = np.flatnonzero(stats[:, cv2.CC_STAT_AREA] >= params.protect_large_area_px)
        large_ids = large_ids[large_ids > 0]
        big_mask = np.isin(labels, large_ids).astype(np.uint8)
        r = params.protect_large_nearby_radius_px
        big_neighborhood = cv2.dilate(big_mask, np.ones((2*r+1, 2*r+1), np.uint8))
        hidden_mask = np.zeros_like(H, dtype=bool)
        for label in range(1, n):
            x, y, w, h, area = (int(v) for v in stats[label])
            key = f"Hlocal_{label:04d}"
            if key not in expected.index:
                raise AssertionError(f"source H candidate missing: {win}/{key}")
            item = expected.loc[key]
            for a, b in [(x, "bbox_x"), (y, "bbox_y"),
                         (w, "bbox_w"), (h, "bbox_h"),
                         (area, "area_px")]:
                if a != int(item[b]):
                    raise AssertionError(f"{win}/{key}: candidate source geometry mismatch {b}")
            local_mask = labels[y:y+h, x:x+w] == label
            points_mask = np.zeros_like(H)
            points_mask[y:y+h, x:x+w] = local_mask
            protected = bool(np.any(big_neighborhood[y:y+h,x:x+w][local_mask]))
            features = local_raw_statistics(tile, H, points_mask,
                                            (x, y, w, h), params)
            status, reason = classify_candidate(area, w, h, features,
                                                 protected, params)
            if status == "suggest_hide":
                hidden_mask[y:y+h, x:x+w] |= local_mask
            records.append({
                "window_id": win, "local_H_id": key,
                "bbox_global_x": origin_x+x, "bbox_global_y": origin_y+y,
                "bbox_w": w, "bbox_h": h, "area_px": area,
                "fused_blackhat_peak_dn": item.fused_blackhat_peak_dn,
                "protected_near_large_H": protected,
                "trial_status": status, "trial_reason": reason, **features,
                "source_H_retained": True,
                "source_result_modified": False,
            })
        remaining_mask = H & ~hidden_mask
        before = overlay(tile, H, f"{win}: original H, {n-1} candidates",
                         (40, 210, 45))
        after = overlay(tile, remaining_mask,
                        f"{win}: shown H (trial display only)", (40, 210, 45))
        suggested = overlay(tile, hidden_mask, f"{win}: suggested hides",
                            (40, 130, 250))
        # Windows下cv2.imwrite可能对包含中文的路径静默返回False。
        # 先编码成PNG，再通过Path.write_bytes写入，并检查生成文件。
        png_path = figures / f"{win}_before_after_suggestions.png"
        encoded_ok, encoded = cv2.imencode(".png", np.hstack([before, after, suggested]))
        if not encoded_ok:
            raise OSError(f"PNG encoding failed: {png_path}")
        png_path.write_bytes(encoded.tobytes())
        if png_path.stat().st_size < 1000:
            raise OSError(f"PNG unexpectedly small: {png_path}")
        counts = {"window_id":win, "source_H_count":n-1,
                  "source_H_pixels":int(H.sum()),
                  "suggested_hidden_pixels":int(hidden_mask.sum()),
                  "display_after_pixels":int(remaining_mask.sum()),
                  "suggested_hidden_components":
                      sum(v["trial_status"]=="suggest_hide" for v in records
                          if v["window_id"]==win)}
        if counts["source_H_pixels"] != (counts["suggested_hidden_pixels"]
                                          + counts["display_after_pixels"]):
            raise AssertionError("trial overlay lost H pixels")
        summaries.append(counts)
        LOG.info("%s: %s", win, counts)
    result = pd.DataFrame.from_records(records)
    if len(result) != len(original):
        raise AssertionError("candidate audit table lost IDs")
    if set(zip(result.window_id, result.local_H_id)) != set(
            zip(original.window_id, original.local_H_id)):
        raise AssertionError("source H ID mismatch")
    result.to_csv(output/"candidate_trial_decisions.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(summaries).to_csv(output/"window_trial_summary.csv", index=False,
                                   encoding="utf-8-sig")
    config = {
        "source":str(source),
        "sample_id":26, "frame_id":1, "trial_parameters":asdict(params),
        "scope":"9 existing manually selected evaluation windows; NOT full frame",
        "status_definitions":{
            "suggest_hide":"only in optional visualization; source H untouched",
            "keep_review":"background unreliable or structure protection",
            "keep":"insufficient evidence to hide under this rule",
        },
    }
    (output/"experiment_config.json").write_text(
        json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    counts=result.trial_status.value_counts().to_dict()
    summary = {
        "total_original_H_components":len(result),
        "source_H_components_preserved":len(result),
        "source_H_pixels_preserved":sum(s["source_H_pixels"] for s in summaries),
        "triage_status_counts":counts,
        "suggested_hidden_pixels":sum(s["suggested_hidden_pixels"] for s in summaries),
        "unreliable_references":int((~result.reference_valid).sum()),
        "window_count":len(summaries),
        "WARNING":"This is NOT false positive rate, not validated against new images.",
    }
    (output/"trial_summary.json").write_text(json.dumps(summary, indent=2,
                             ensure_ascii=False), encoding="utf-8")
    LOG.info("OUTPUT %s", output)
    LOG.info("SUMMARY %s", summary)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--run-id", default="run_20261010_small_raw_contrast_v1")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    params = NoiseTrialConfig(
        small_area_max_px=cfg.CASE03F_SMALL_AREA_MAX_PX,
        min_relative_contrast=cfg.CASE03F_MIN_RELATIVE_CONTRAST,
        min_significance_z=cfg.CASE03F_MIN_SIGNIFICANCE_Z,
        ring_outer_radius_px=cfg.CASE03F_RING_OUTER_RADIUS_PX,
        ring_inner_guard_px=cfg.CASE03F_RING_INNER_GUARD_PX,
        ring_min_count=cfg.CASE03F_RING_MIN_COUNT,
        sigma_floor_dn=cfg.CASE03F_SIGMA_FLOOR_DN,
        protect_large_nearby_radius_px=cfg.CASE03F_PROTECT_LARGE_NEARBY_RADIUS_PX,
        protect_large_area_px=cfg.CASE03F_PROTECT_LARGE_AREA_PX,
    )
    run(args.source, args.run_id, params)
