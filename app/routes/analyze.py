import os
import base64
import tempfile
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from fastapi.responses import JSONResponse, PlainTextResponse
from app.services.llm_service import plan_actions
from app.services.ocr_service import run_ocr
from app.services.vision_service import analyze_ui
from pydantic import BaseModel
from PIL import Image
from io import BytesIO

from .. import auth, models

router = APIRouter()

@router.post("/analyze")
async def analyze_screen_file(
    file: UploadFile = File(...),
    question: str = Form(...),
    current_user: models.User = Depends(auth.get_current_user)
):
    """
    Standard analysis endpoint for uploaded files (Keeping this unchanged)
    """
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name

        ocr_items = run_ocr(tmp_path)
        vision = analyze_ui(tmp_path)
        result = plan_actions(vision, ocr_items, question)

        with Image.open(tmp_path) as img:
            width, height = img.size
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            image_base64 = base64.b64encode(buffered.getvalue()).decode()

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
        # Avoid leaking internal error details
        print(f"Error in analyze_screen_file: {e}")
        raise HTTPException(status_code=500, detail="An error occurred during screen analysis")

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


# -------- NEW LIVE SCREEN ANALYSIS ENDPOINT -------- #
class AnalyzeLiveRequest(BaseModel):
    image_base64: str
    question: str

@router.post("/analyze_live")
async def analyze_live(
    req: AnalyzeLiveRequest,
    current_user: models.User = Depends(auth.get_current_user)
):
    tmp_path = None
    try:
        # Decode image
        image_data = req.image_base64.split(",")[-1]
        image_bytes = base64.b64decode(image_data)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name

        # Run Analysis
        ocr_items = run_ocr(tmp_path)
        vision = analyze_ui(tmp_path)
        result = plan_actions(vision, ocr_items, req.question)

        steps = result.get("steps", [])
        
        # Format the list into a single string with newlines
        if isinstance(steps, list) and steps:
            formatted_text = "\n".join([f"{i+1}. {step}" for i, step in enumerate(steps)])
        else:
            formatted_text = result.get("text", "Sorry, I couldn't find any steps.")

        # 🆕 RETURN RAW TEXT: No JSON structure, just the string.
        return JSONResponse(content=formatted_text)

    except Exception as e:
        # Avoid leaking internal error details
        print(f"Error in analyze_live: {e}")
        raise HTTPException(status_code=500, detail="An error occurred during live analysis")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)