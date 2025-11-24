# app/services/vision_service.py
from PIL import Image
import numpy as np

def analyze_ui(image_path: str):
    """
    Very small heuristic: return image size and top-level
    bounding boxes of text elements (from OCR you passed).
    For now just return image dims — later call GPT-4V or another vision model.
    """
    img = Image.open(image_path)
    w, h = img.size
    return {"width": w, "height": h, "note": "replace with GPT-4V or YOLO-based UI detection"}
