# app/utils/image_utils.py
from PIL import Image, ImageDraw

def draw_boxes(image_path, boxes, out_path):
    img = Image.open(image_path).convert("RGBA")
    draw = ImageDraw.Draw(img)
    for b in boxes:
        left, top, right, bottom = b
        draw.rectangle([left, top, right, bottom], outline="red", width=3)
    img.save(out_path)
