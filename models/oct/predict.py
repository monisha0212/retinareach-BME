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
    load_dotenv(dotenv_path=ENV_PATH)
except ImportError:
    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip("'\"")
                    if k not in os.environ:
                        os.environ[k] = v

API_KEY = os.getenv("ROBOFLOW_API_KEY", "eIDi2YQLr67wAKIQNAa7")
API_URL = os.getenv("ROBOFLOW_API_URL", "https://serverless.roboflow.com").rstrip("/")
WORKSPACE_NAME = os.getenv("WORKSPACE_NAME", "bhavan-i-iyyappan")
WORKFLOW_ID = os.getenv("WORKFLOW_OCT", "general-segmentation-api-4")

try:
    from inference_sdk import InferenceHTTPClient, InferenceConfiguration
    client = InferenceHTTPClient(
        api_url=API_URL,
        api_key=API_KEY
    ).configure(InferenceConfiguration(
        api_key_transport="header"
    ))
except ImportError:
    client = None


def _run_workflow_http(img_pil: Image.Image):
    buf = io.BytesIO()
    img_pil.save(buf, format="JPEG", quality=90)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    url = f"{API_URL}/{WORKSPACE_NAME}/workflows/{WORKFLOW_ID}"
    resp = requests.post(
        url,
        json={
            "api_key": API_KEY,
            "inputs": {
                "image": {"type": "base64", "value": b64},
                "classes": "NORMAL, CNV, DME, DRUSEN"
            }
        },
        timeout=30
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("outputs", [data])


def predict(image_path) -> dict:
    """
    Runs OCT retinal classification/segmentation on an image.
    Exposes `predict(image_path) -> dict`.
    Returns structured predictions (e.g. NORMAL, CNV, DME, DRUSEN).
    """
    img_input = image_path
    if isinstance(image_path, (str, Path)):
        if not os.path.exists(str(image_path)):
            raise FileNotFoundError(f"Image not found at path: {image_path}")
        img_input = Image.open(str(image_path)).convert("RGB")
    elif isinstance(image_path, Image.Image):
        img_input = image_path.convert("RGB")

    if client is not None:
        result = client.run_workflow(
            workspace_name=WORKSPACE_NAME,
            workflow_id=WORKFLOW_ID,
            images={"image": img_input},
            parameters={"classes": "NORMAL, CNV, DME, DRUSEN"},
            use_cache=True
        )
    else:
        result = _run_workflow_http(img_input)

    top_class = "NORMAL"
    confidence = 0.0
    all_predictions = []
    inference_time = None

    try:
        if isinstance(result, list) and len(result) > 0:
            first = result[0]
            preds_block = first.get("predictions", {}) if isinstance(first, dict) else {}
            if isinstance(preds_block, dict):
                top_class = preds_block.get("top") or preds_block.get("class") or preds_block.get("label") or top_class
                confidence = preds_block.get("confidence", 0.0)
                inference_time = preds_block.get("time")
                all_preds = preds_block.get("predictions", [])
                if isinstance(all_preds, list) and len(all_preds) > 0:
                    for p in all_preds:
                        if isinstance(p, dict):
                            all_predictions.append({
                                "class": p.get("class") or p.get("label", "Unknown"),
                                "confidence": p.get("confidence", 0.0),
                                "class_id": p.get("class_id")
                            })
            if isinstance(first, dict):
                for k, v in first.items():
                    if k != "predictions" and isinstance(v, dict):
                        if "class" in v or "top" in v:
                            top_class = v.get("top") or v.get("class") or top_class
                            confidence = v.get("confidence") or confidence
    except Exception:
        pass

    return {
        "status": "success",
        "model_type": "oct",
        "top_class": top_class,
        "confidence": confidence,
        "inference_time": inference_time,
        "all_predictions": all_predictions,
        "raw_result": result
    }
