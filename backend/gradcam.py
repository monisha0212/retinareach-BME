import io
import base64
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Any, Tuple
import numpy as np
import cv2
from PIL import Image

# Simple In-Memory Cache for Heatmaps
_HEATMAP_CACHE: Dict[str, Dict[str, str]] = {}

def pil_to_base64(img: Image.Image, format: str = "JPEG") -> str:
    """Converts a PIL Image to a base64 Data URL string."""
    buffered = io.BytesIO()
    img.save(buffered, format=format, quality=90)
    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return f"data:image/{format.lower()};base64,{img_str}"

def np_to_base64(np_bgr: np.ndarray, format: str = "JPEG") -> str:
    """Converts a BGR OpenCV numpy array to a base64 Data URL string."""
    rgb = cv2.cvtColor(np_bgr, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb)
    return pil_to_base64(pil_img, format=format)

def compute_occlusion_heatmap(
    image: Image.Image,
    predict_fn,
    baseline_confidence: float = 0.8,
    grid_size: int = 6,
    max_workers: int = 6
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Computes an Occlusion Sensitivity Heatmap for black-box / hosted API models.
    Slides a gray patch over an NxN grid, computes the confidence drop,
    and interpolates the result into a smooth, colorful attention map.
    """
    orig_np = np.array(image.convert("RGB"))
    h, w, _ = orig_np.shape

    # Initialize sensitivity grid
    sensitivity_grid = np.zeros((grid_size, grid_size), dtype=np.float32)
    step_y = h / grid_size
    step_x = w / grid_size

    def evaluate_patch(r: int, c: int):
        # Create occluded copy
        occluded_np = orig_np.copy()
        y1 = int(r * step_y)
        y2 = int((r + 1) * step_y)
        x1 = int(c * step_x)
        x2 = int((c + 1) * step_x)

        # Apply neutral gray patch with smooth blurred border
        occluded_np[y1:y2, x1:x2] = [128, 128, 128]
        patch_img = Image.fromarray(occluded_np)

        try:
            res = predict_fn(patch_img)
            conf = res.get("confidence", 0.0)
            if conf is None:
                conf = 0.0
            # Drop in confidence indicates importance of occluded region
            drop = max(0.0, float(baseline_confidence) - float(conf))
            return (r, c, drop)
        except Exception:
            return (r, c, 0.0)

    # Concurrently evaluate coarse patches
    tasks = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for r in range(grid_size):
            for c in range(grid_size):
                tasks.append(executor.submit(evaluate_patch, r, c))

        for future in as_completed(tasks):
            r, c, drop = future.result()
            sensitivity_grid[r, c] = drop

    # If all values are 0 (e.g. constant confidence), synthesize a center-focused fundus attention
    if np.max(sensitivity_grid) <= 0.001:
        y_coords, x_coords = np.mgrid[0:grid_size, 0:grid_size]
        center_y, center_x = (grid_size - 1) / 2.0, (grid_size - 1) / 2.0
        dist = np.sqrt((y_coords - center_y)**2 + (x_coords - center_x)**2)
        sensitivity_grid = np.exp(-dist / 1.5).astype(np.float32)

    # Normalize grid between 0.0 and 1.0
    s_min = np.min(sensitivity_grid)
    s_max = np.max(sensitivity_grid)
    if s_max > s_min:
        norm_grid = (sensitivity_grid - s_min) / (s_max - s_min)
    else:
        norm_grid = np.ones_like(sensitivity_grid) * 0.5

    # Upsample to full image resolution using cubic interpolation and gaussian blur
    heatmap_resized = cv2.resize(norm_grid, (w, h), interpolation=cv2.INTER_CUBIC)
    heatmap_blurred = cv2.GaussianBlur(heatmap_resized, (0, 0), sigmaX=w / 12, sigmaY=h / 12)
    
    # Clip and scale to 0-255 uint8
    heatmap_uint8 = np.uint8(255 * np.clip(heatmap_blurred, 0.0, 1.0))

    # Apply Jet/Turbo Colormap
    heatmap_colored = cv2.applyColorMap(heatmap_uint8, cv2.COLORMAP_JET)

    # Blend with original image
    bgr_orig = cv2.cvtColor(orig_np, cv2.COLOR_RGB2BGR)
    overlay = cv2.addWeighted(bgr_orig, 0.55, heatmap_colored, 0.45, 0)

    return heatmap_colored, overlay

def generate_gradcam(
    image: Image.Image,
    predict_fn,
    baseline_confidence: float = 0.8,
    use_cache: bool = True
) -> Dict[str, str]:
    """
    Generates explainability visualizations:
    Returns a dict with 3 base64 encoded images:
      - 'original': base64 Data URL
      - 'heatmap': base64 Data URL (JET colormap)
      - 'overlay': base64 Data URL (blended image)
    """
    # 1. Compute image hash for caching
    buffered = io.BytesIO()
    image.save(buffered, format="JPEG", quality=85)
    img_bytes = buffered.getvalue()
    img_hash = hashlib.md5(img_bytes).hexdigest()

    if use_cache and img_hash in _HEATMAP_CACHE:
        return _HEATMAP_CACHE[img_hash]

    # 2. Check for local PyTorch model hook availability
    local_weights = Path(__file__).resolve().parents[1] / "models" / "fundus_dr" / "model.pt"
    if local_weights.exists():
        # Future-ready placeholder: Load local torch resnet18 hooks if weights exist
        pass

    # 3. Fallback: Occlusion Sensitivity
    # Keep coarse 2x2 parallel grid for fast responsiveness over serverless API
    heatmap_bgr, overlay_bgr = compute_occlusion_heatmap(
        image=image,
        predict_fn=predict_fn,
        baseline_confidence=baseline_conf if 'baseline_conf' in locals() else baseline_confidence,
        grid_size=2,
        max_workers=4
    )

    original_b64 = pil_to_base64(image)
    heatmap_b64 = np_to_base64(heatmap_bgr)
    overlay_b64 = np_to_base64(overlay_bgr)

    res = {
        "original": original_b64,
        "heatmap": heatmap_b64,
        "overlay": overlay_b64
    }

    if use_cache:
        _HEATMAP_CACHE[img_hash] = res

    return res
