# app/routes/stream_ws.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import base64
import tempfile
from app.services.ocr_service import run_ocr
from app.services.vision_service import analyze_ui
from app.services.llm_service import plan_actions

router = APIRouter()

@router.websocket("/screen")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()  # expects JSON with base64 image and question
            import json
            payload = json.loads(data)
            b64 = payload.get("image")
            question = payload.get("question", "")
            if not b64:
                await websocket.send_text(json.dumps({"error":"no image"}))
                continue

            # decode
            header, b64data = (b64.split(",", 1) if "," in b64 else (None, b64))
            img_bytes = base64.b64decode(b64data)
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
                tf.write(img_bytes)
                tmp_path = tf.name

            ocr_items = run_ocr(tmp_path)
            vision = analyze_ui(tmp_path)
            llm_response = plan_actions(vision, ocr_items, question)

            await websocket.send_text(json.dumps({
                "ocr": ocr_items,
                "vision": vision,
                "llm": llm_response
            }))
    except WebSocketDisconnect:
        print("client disconnected")
