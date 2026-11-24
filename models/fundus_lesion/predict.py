import io
import os
import base64
import requests
from pathlib import Path
from PIL import Image

# Load .env
ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=ENV_PATH, override=True)
except ImportError:
    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip("'\"")
                    os.environ[k] = v

API_KEY = os.getenv("ROBOFLOW_API_KEY", "eIDi2YQLr67wAKIQNAa7")
API_URL = os.getenv("ROBOFLOW_API_URL", "https://serverless.roboflow.com").rstrip("/")
WORKSPACE_NAME = os.getenv("WORKSPACE_NAME", "bhavan-i-iyyappan")
WORKFLOW_ID = os.getenv("WORKFLOW_LESION", "lesion_detection-91wo9")
MODEL_ID = os.getenv("MODEL_LESION", "lesion_detection-91wo9/2")

LESION_LABELS = {
    "MA": "Microaneurysm (MA)",
    "HEM": "Hemorrhage (HEM)",
    "HE": "Hard Exudate (HE)",
    "SE": "Soft Exudate (SE)",
}


def _encode_jpeg_b64(img_pil: Image.Image) -> str:
    buf = io.BytesIO()
    img_pil.save(buf, format="JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _run_direct_detect(img_pil: Image.Image) -> dict:
    b64 = _encode_jpeg_b64(img_pil)
    url = f"https://detect.roboflow.com/{MODEL_ID}?api_key={API_KEY}&confidence=18"
    resp = requests.post(
        url,
        data=b64,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15
    )
    resp.raise_for_status()
    return resp.json()


def _run_workflow_http(img_pil: Image.Image):
    b64 = _encode_jpeg_b64(img_pil)
    url = f"{API_URL}/{WORKSPACE_NAME}/workflows/{WORKFLOW_ID}"
    resp = requests.post(
        url,
        json={
            "api_key": API_KEY,
            "inputs": {
                "image": {"type": "base64", "value": b64}
            }
        },
        timeout=20
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("outputs", [data])


def predict(image_path) -> dict:
    """
    Runs retinal lesion detection (MA, HEM, HE, SE) on a fundus image.
    Returns structured bounding boxes, detections, and lesion summary.
    """
    img_input = image_path
    if isinstance(image_path, (str, Path)):
        if not os.path.exists(str(image_path)):
            raise FileNotFoundError(f"Image not found at path: {image_path}")
        img_input = Image.open(str(image_path)).convert("RGB")
    elif isinstance(image_path, Image.Image):
        img_input = image_path.convert("RGB")

    detections = []
    summary_label = "No Focal Lesions Detected"
    result = None

    try:
        direct = _run_direct_detect(img_input)
        result = [{"predictions": direct}]
        boxes = direct.get("predictions", [])
    except Exception:
        try:
            result = _run_workflow_http(img_input)
            boxes = []
            if isinstance(result, list) and len(result) > 0:
                preds_block = result[0].get("predictions", {})
                if isinstance(preds_block, dict):
                    boxes = preds_block.get("predictions", [])
        except Exception as e:
            result = [{"error": str(e)}]
            boxes = []

    if isinstance(boxes, list):
        for box in boxes:
            if isinstance(box, dict) and "x" in box and "width" in box:
                raw_cls = str(box.get("class") or box.get("label") or "Lesion")
                detections.append({
                    "class": LESION_LABELS.get(raw_cls, raw_cls),
                    "raw_class": raw_cls,
                    "confidence": box.get("confidence", 0.0),
                    "x": box.get("x", 0),
                    "y": box.get("y", 0),
                    "width": box.get("width", 0),
                    "height": box.get("height", 0),
                    "points": box.get("points", [])
                })

    if detections:
        counts = {}
        for d in detections:
            rc = d.get("raw_class") or d.get("class")
            counts[rc] = counts.get(rc, 0) + 1
        summary_label = ", ".join(f"{k}: {v}" for k, v in counts.items())

    return {
        "status": "success",
        "model_type": "fundus_lesion",
        "detections": detections,
        "detection_count": len(detections),
        "summary": summary_label,
        "raw_result": result
    }
