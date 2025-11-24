import os
import base64
import tempfile
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from app.services.llm_service import plan_actions
from app.services.ocr_service import run_ocr
from app.services.vision_service import analyze_ui
from pydantic import BaseModel
from PIL import Image
from io import BytesIO
from PIL import Image

router = APIRouter()


@router.post("/analyze")
async def analyze_screen_file(
    file: UploadFile = File(...),
    question: str = Form(...)
):
    """
    Endpoint that:
    1. Accepts a screenshot (image)
    2. Accepts a user question about the interface
    3. Runs OCR + Vision analysis
    4. Passes data + question to LLM for step planning
    """
    tmp_path = None
    try:
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name

        # OCR + Vision
        ocr_items = run_ocr(tmp_path)
        vision = analyze_ui(tmp_path)
        result = plan_actions(vision, ocr_items, question)

        # Load image for metadata
        with Image.open(tmp_path) as img:
            width, height = img.size
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            image_base64 = base64.b64encode(buffered.getvalue()).decode()

        # Return combined response
        return {
            "success": True,
            "result": {
                **result,
                "image_base64": image_base64,
                "image_width": width,
                "image_height": height,
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


# -------- NEW LIVE SCREEN ANALYSIS ENDPOINT -------- #
class AnalyzeLiveRequest(BaseModel):
    image_base64: str
    question: str


@router.post("/analyze_live")
async def analyze_live(req: AnalyzeLiveRequest):
    tmp_path = None
    try:
        image_data = req.image_base64.split(",")[-1]
        image_bytes = base64.b64decode(image_data)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name

        # Get image dimensions
        img = Image.open(tmp_path)
        width, height = img.size

        ocr_items = run_ocr(tmp_path)
        vision = analyze_ui(tmp_path)
        result = plan_actions(vision, ocr_items, req.question)

        # 🆕 Add image data for frontend alignment
        return {
            "success": True,
            "result": {
                **result,
                "image_base64": req.image_base64,
                "image_width": width,
                "image_height": height
            }
        }

    except Exception as e:
        print("Error in analyze_live:", e)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
