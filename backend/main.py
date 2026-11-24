import io
import os
import sys
import logging
import traceback
from pathlib import Path
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image

# Ensure project root is in python path
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Import models & gradcam
from models.fundus_dr.predict import predict as predict_dr
from models.fundus_lesion.predict import predict as predict_lesion
from models.oct.predict import predict as predict_oct
from backend.gradcam import generate_gradcam

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backend")

app = FastAPI(
    title="Retinal Image Analysis API",
    description="Demo platform for Fundus (DR & Lesion + Grad-CAM) and OCT Retinal Classification",
    version="1.0.0"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Paths
FRONTEND_DIR = ROOT_DIR / "frontend"
INDEX_HTML = FRONTEND_DIR / "index.html"

# Mount static frontend directory
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

@app.get("/", response_class=FileResponse)
async def serve_index():
    """Serves the frontend single-page application."""
    if INDEX_HTML.exists():
        return FileResponse(str(INDEX_HTML))
    return HTMLResponse("<h1>Frontend index.html not found</h1>", status_code=404)

def read_and_validate_image(file: UploadFile, contents: bytes) -> Image.Image:
    """Helper to validate and decode uploaded file bytes into a RGB PIL Image."""
    if not contents or len(contents) == 0:
        raise HTTPException(status_code=400, detail="The uploaded image file is empty.")
    try:
        image = Image.open(io.BytesIO(contents)).convert("RGB")
        return image
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid image format: {str(e)}. Please upload a valid JPG, PNG, or WEBP image."
        )

@app.post("/predict/fundus")
async def predict_fundus_endpoint(file: UploadFile = File(...)):
    """
    Endpoint for Fundus Image Analysis:
    - Runs DR classification
    - Runs Lesion detection/segmentation
    - Generates Explainable AI Grad-CAM (original, heatmap, overlay)
    """
    logger.info(f"[POST /predict/fundus] Processing: {file.filename}")
    try:
        contents = await file.read()
        image = read_and_validate_image(file, contents)

        # 1. Run Fundus DR model
        try:
            dr_result = predict_dr(image)
        except Exception as e:
            logger.error(f"DR model error: {e}")
            dr_result = {"status": "error", "error": str(e), "top_class": "Error", "confidence": 0.0}

        # 2. Run Fundus Lesion model
        try:
            lesion_result = predict_lesion(image)
        except Exception as e:
            logger.error(f"Lesion model error: {e}")
            lesion_result = {"status": "error", "error": str(e), "detections": []}

        # 3. Generate Grad-CAM / Explainability Heatmap
        try:
            baseline_conf = dr_result.get("confidence", 0.75) or 0.75
            gradcam_maps = generate_gradcam(
                image=image,
                predict_fn=predict_dr,
                baseline_confidence=baseline_conf,
                use_cache=True
            )
        except Exception as e:
            logger.error(f"GradCAM generation error: {e}")
            gradcam_maps = {"error": str(e)}

        return JSONResponse(content={
            "success": True,
            "filename": file.filename,
            "image_size": list(image.size),
            "dr": dr_result,
            "lesion": lesion_result,
            "gradcam": gradcam_maps
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Internal server error in /predict/fundus: {traceback.format_exc()}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to process fundus image: {str(e)}"}
        )

@app.post("/predict/oct")
async def predict_oct_endpoint(file: UploadFile = File(...)):
    """
    Endpoint for Optical Coherence Tomography (OCT) Analysis:
    - Runs OCT classification (NORMAL, CNV, DME, DRUSEN)
    """
    logger.info(f"[POST /predict/oct] Processing: {file.filename}")
    try:
        contents = await file.read()
        image = read_and_validate_image(file, contents)

        # Run OCT Model
        try:
            oct_result = predict_oct(image)
        except Exception as e:
            logger.error(f"OCT model error: {e}")
            return JSONResponse(
                status_code=502,
                content={"error": f"OCT Model error: {str(e)}"}
            )

        return JSONResponse(content={
            "success": True,
            "filename": file.filename,
            "image_size": list(image.size),
            "oct": oct_result
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Internal server error in /predict/oct: {traceback.format_exc()}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to process OCT image: {str(e)}"}
        )

if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("🚀 Retinal AI Diagnostic Server running at http://127.0.0.1:8080")
    print("=" * 60)
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8080, reload=True)
