# app/services/ocr_service.py
from PIL import Image
import pytesseract

def run_ocr(image_path: str):
    """
    Return a list of dict: [{text, box: [x1,y1,x2,y2], conf}, ...]
    """
    img = Image.open(image_path).convert("RGB")
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

    items = []
    n = len(data['text'])
    for i in range(n):
        txt = data['text'][i].strip()
        if not txt:
            continue
        items.append({
            "text": txt,
            "conf": float(data['conf'][i]),
            "box": [int(data['left'][i]), int(data['top'][i]),
                    int(data['left'][i] + data['width'][i]), int(data['top'][i] + data['height'][i])]
        })
    return items
