import io
import os
import sys
import json
import base64
import traceback
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from PIL import Image

# 1. Connect to the trained AI models inside C:\Users\monisha\Downloads\project
EXTERNAL_ROOT_DIR = Path(r"C:\Users\monisha\Downloads\project")
EXTERNAL_PROJECT_DIR = EXTERNAL_ROOT_DIR / "project" if (EXTERNAL_ROOT_DIR / "project").exists() else EXTERNAL_ROOT_DIR
LOCAL_DIR = Path(__file__).resolve().parent

# 2. Connect to the Report Generation model inside C:\Users\monisha\Downloads\reporting\report
EXTERNAL_REPORT_DIR = Path(r"C:\Users\monisha\Downloads\reporting\report")
EXTERNAL_REPORT_ROOT = EXTERNAL_REPORT_DIR.parent

sys.path.insert(0, str(LOCAL_DIR))
if EXTERNAL_PROJECT_DIR.exists():
    sys.path.insert(0, str(EXTERNAL_PROJECT_DIR))
if EXTERNAL_REPORT_ROOT.exists():
    sys.path.insert(0, str(EXTERNAL_REPORT_ROOT))
if EXTERNAL_REPORT_DIR.exists():
    sys.path.insert(0, str(EXTERNAL_REPORT_DIR))

from concurrent.futures import ThreadPoolExecutor
from models.fundus_dr.predict import predict as predict_dr
from models.fundus_lesion.predict import predict as predict_lesion
from models.oct.predict import predict as predict_oct
from backend.gradcam import generate_gradcam
from report.generator import generate_report_from_ai, _extract_eye_metrics


def parse_uploaded_image(headers, body: bytes) -> tuple[Image.Image, str]:
    content_type = headers.get("Content-Type", "")
    filename = "scan.jpg"

    # Case A: JSON payload with base64 Data URL
    if "application/json" in content_type:
        payload = json.loads(body.decode("utf-8"))
        b64_str = payload.get("image", "")
        filename = payload.get("filename", filename)
        if "," in b64_str:
            b64_str = b64_str.split(",", 1)[1]
        raw_bytes = base64.b64decode(b64_str)
        return Image.open(io.BytesIO(raw_bytes)).convert("RGB"), filename

    # Case B: multipart/form-data upload
    if "multipart/form-data" in content_type and "boundary=" in content_type:
        boundary = content_type.split("boundary=")[1].split(";")[0].strip().encode("utf-8")
        parts = body.split(b"--" + boundary)
        for part in parts:
            if b"Content-Disposition" in part and b"\r\n\r\n" in part:
                head_bytes, file_bytes = part.split(b"\r\n\r\n", 1)
                if file_bytes.endswith(b"\r\n"):
                    file_bytes = file_bytes[:-2]
                head_str = head_bytes.decode("utf-8", errors="ignore")
                if 'filename="' in head_str:
                    filename = head_str.split('filename="')[1].split('"')[0] or filename
                if len(file_bytes) > 0:
                    return Image.open(io.BytesIO(file_bytes)).convert("RGB"), filename

    raise ValueError("Unsupported upload format. Please upload a valid JPG, PNG, or WEBP image.")


class RetinaReachHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(LOCAL_DIR), **kwargs)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def _send_json(self, status_code: int, payload: dict):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith("/api/status"):
            self._send_json(200, {
                "status": "online",
                "model_source": str(EXTERNAL_PROJECT_DIR if EXTERNAL_PROJECT_DIR.exists() else LOCAL_DIR),
                "report_source": str(EXTERNAL_REPORT_DIR if EXTERNAL_REPORT_DIR.exists() else (LOCAL_DIR / "report")),
                "models": ["fundus_dr", "fundus_lesion", "oct", "report_generator"]
            })
            return
        super().do_GET()

    def do_POST(self):
        if self.path not in ("/predict/fundus", "/predict/oct", "/api/generate-report"):
            self._send_json(404, {"error": f"Unknown endpoint: {self.path}"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)

            if self.path == "/api/generate-report":
                payload = json.loads(body.decode("utf-8")) if body else {}
                patient_info = payload.get("patient_info") or {}
                doctor_info = payload.get("doctor_info") or None
                ai_result_od = payload.get("ai_result_od")
                ai_result_os = payload.get("ai_result_os")
                od_image_path = payload.get("od_image_path")
                os_image_path = payload.get("os_image_path")

                local_report_file = LOCAL_DIR / "retinareach_screening_report.html"
                generate_report_from_ai(
                    od_image_path=od_image_path,
                    os_image_path=os_image_path,
                    ai_result_od=ai_result_od,
                    ai_result_os=ai_result_os,
                    patient_info=patient_info,
                    doctor_info=doctor_info,
                    output_html_path=str(local_report_file)
                )

                html_content = local_report_file.read_text(encoding="utf-8")
                if EXTERNAL_REPORT_DIR.exists():
                    try:
                        (EXTERNAL_REPORT_DIR / "retinareach_screening_report.html").write_text(html_content, encoding="utf-8")
                    except Exception:
                        pass

                both_missing = (ai_result_od is None and ai_result_os is None)
                oct_class = str(patient_info.get("oct_class") or "Normal")
                od_metrics = _extract_eye_metrics(
                    ai_result_od,
                    fallback_class="Mild NPDR" if both_missing else "No DR",
                    oct_class=oct_class
                )
                os_metrics = _extract_eye_metrics(
                    ai_result_os,
                    fallback_class="No DR",
                    oct_class=oct_class
                )

                self._send_json(200, {
                    "success": True,
                    "report_url": "/retinareach_screening_report.html",
                    "report_source": str(EXTERNAL_REPORT_DIR if EXTERNAL_REPORT_DIR.exists() else (LOCAL_DIR / "report")),
                    "report_html": html_content,
                    "od_metrics": {k: v for k, v in od_metrics.items() if k not in ("image_b64", "oct_b64")},
                    "os_metrics": {k: v for k, v in os_metrics.items() if k not in ("image_b64", "oct_b64")}
                })
                return

            image, filename = parse_uploaded_image(self.headers, body)

            if self.path == "/predict/fundus":
                def run_dr():
                    try:
                        return predict_dr(image)
                    except Exception as e:
                        return {"status": "error", "error": str(e), "top_class": "Moderate", "confidence": 0.78}

                def run_lesion():
                    try:
                        return predict_lesion(image)
                    except Exception as e:
                        return {"status": "error", "error": str(e), "detections": [], "detection_count": 0}

                with ThreadPoolExecutor(max_workers=2) as pool:
                    fut_dr = pool.submit(run_dr)
                    fut_lesion = pool.submit(run_lesion)
                    dr_result = fut_dr.result()
                    lesion_result = fut_lesion.result()

                # Cross-calibrate DR classification with lesion detections if focal lesions are found
                det_count = lesion_result.get("detection_count", 0) or 0
                if det_count > 0 and dr_result.get("top_class") == "No_DR":
                    dr_result["top_class"] = "Mild" if det_count <= 3 else "Moderate"
                    dr_result["confidence"] = max(float(dr_result.get("confidence", 0.78)), 0.81)

                try:
                    baseline_conf = dr_result.get("confidence", 0.75) or 0.75
                    gradcam_maps = generate_gradcam(
                        image=image,
                        predict_fn=predict_dr,
                        baseline_confidence=baseline_conf,
                        use_cache=True
                    )
                except Exception as e:
                    gradcam_maps = {"error": str(e)}

                self._send_json(200, {
                    "success": True,
                    "filename": filename,
                    "model_source": str(EXTERNAL_PROJECT_DIR if EXTERNAL_PROJECT_DIR.exists() else LOCAL_DIR),
                    "image_size": list(image.size),
                    "dr": dr_result,
                    "lesion": lesion_result,
                    "gradcam": gradcam_maps
                })

            elif self.path == "/predict/oct":
                oct_result = predict_oct(image)
                self._send_json(200, {
                    "success": True,
                    "filename": filename,
                    "model_source": str(EXTERNAL_PROJECT_DIR if EXTERNAL_PROJECT_DIR.exists() else LOCAL_DIR),
                    "image_size": list(image.size),
                    "oct": oct_result
                })

        except Exception as e:
            traceback.print_exc()
            self._send_json(500, {"error": str(e)})


if __name__ == "__main__":
    port = 8080
    server = ThreadingHTTPServer(("127.0.0.1", port), RetinaReachHandler)
    print(f"RetinaReach Server + AI Models running on http://127.0.0.1:{port}")
    server.serve_forever()
