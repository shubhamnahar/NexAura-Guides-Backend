# app/routes/guides.py
from fastapi import APIRouter, Depends, HTTPException, status,Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Dict, Any
from io import BytesIO
import base64
import os
from pathlib import Path
from PIL import Image, ImageDraw

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from .. import database, models, auth
from ..schemas import GuideCreate, Guide
import json
from fastapi import BackgroundTasks

router = APIRouter()

# Where screenshots will be stored on disk (relative to your app root)
SCREENSHOT_ROOT = Path("guide_screenshots")


# --- EXPORT GUIDE AS PDF (WITH IMAGES) ---
@router.get("/{guide_id}/export-pdf")
async def export_guide_pdf(
    guide_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Generate a PDF document for a single guide.

    PDF includes:
      - Guide name
      - Shortcut
      - Description
      - Numbered list of steps
      - Screenshot per step (if available)
    """
    # 1. Load guide with steps
    db_guide = (
        db.query(models.Guide)
        .filter(models.Guide.id == guide_id)
        .first()
    )

    if not db_guide:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Guide not found",
        )

    # 2. Ensure user owns this guide
    if db_guide.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to export this guide",
        )

    # 3. Build PDF in memory
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    margin_left = 50
    margin_top = height - 50
    line_height = 16

    def new_page():
        nonlocal margin_top
        pdf.showPage()
        margin_top = height - 50

    def ensure_space(lines: int = 1):
        nonlocal margin_top
        needed = lines * line_height
        if margin_top - needed < 50:
            new_page()

    def write_line(text: str = ""):
        nonlocal margin_top
        ensure_space(1)
        pdf.drawString(margin_left, margin_top, text)
        margin_top -= line_height

    # Title
    pdf.setFont("Helvetica-Bold", 18)
    write_line(f"Guide: {db_guide.name}")

    pdf.setFont("Helvetica", 12)
    write_line(f"Shortcut: {db_guide.shortcut}")
    write_line("")

    # Description
    write_line("Description:")
    desc = db_guide.description or ""
    max_chars = 90
    for i in range(0, len(desc), max_chars):
        write_line(desc[i : i + max_chars])
    write_line("")
    write_line("Steps:")
    write_line("")

    # Steps ordered by step_number
    steps = sorted(db_guide.steps, key=lambda s: s.step_number)

    if not steps:
        write_line("No steps recorded for this guide.")
    else:
        for step in steps:
            write_line(f"Step {step.step_number}: {step.instruction}")
            selector = step.selector or ""
            write_line(f"  Selector:")
            for i in range(0, len(selector), max_chars):
                write_line("    " + selector[i : i + max_chars])

            # If there is a screenshot, embed it
            if step.screenshot_path and os.path.exists(step.screenshot_path):
                # leave a bit of space
                ensure_space(10)  # approx area for image
                img_x = margin_left
                img_width = width - margin_left * 2
                img_height = 200  # fixed height

                try:
                    pdf.drawImage(
                        step.screenshot_path,
                        img_x,
                        margin_top - img_height,
                        width=img_width,
                        height=img_height,
                        preserveAspectRatio=True,
                        mask="auto",
                    )
                    margin_top -= (img_height + 10)
                    print("&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&helllllooooo----------------------------------------------------")
                    # DRAW HIGHLIGHT IF PRESENT
                    # if (
                    #     step.highlight_x is not None
                    #     and step.highlight_y is not None
                    #     and step.highlight_width is not None
                    #     and step.highlight_height is not None
                    # ):
                    #     pdf.setFillColorRGB(1, 1, 0, alpha=0.3)

                    #     # Convert DOM coords to PDF coords
                    #     dom_x = step.highlight_x
                    #     dom_y = step.highlight_y
                    #     dom_w = step.highlight_width
                    #     dom_h = step.highlight_height
                    #     print("dom_x--------"+step.highlight_x)

                    #     pdf_x = img_x + dom_x
                    #     pdf_y = (margin_top - img_height) + (img_height - dom_y - dom_h)

                    #     pdf.rect(
                    #         pdf_x,
                    #         pdf_y,
                    #         dom_w,
                    #         dom_h,
                    #         fill=1,
                    #         stroke=0
                    #     )

                    
                except Exception as e:
                    # Don't break PDF if image fails
                    write_line(f"  [Could not render screenshot: {e}]")
            write_line("")

    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    filename = f"guide-{guide_id}.pdf"

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --- DELETE ENDPOINT ---
@router.delete("/{guide_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_guide(
    guide_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    db_guide = db.query(models.Guide).filter(models.Guide.id == guide_id).first()
    if not db_guide:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Guide not found"
        )

    if db_guide.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this guide",
        )

    try:
        db.delete(db_guide)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting guide: {e}",
        )
    return None


# --- PUBLIC SEARCH ENDPOINT ---
@router.get("/public", response_model=List[Guide])
async def search_public_guides(
    search: str = "", db: Session = Depends(database.get_db)
):
    if search:
        search_term = f"%{search}%"
        return (
            db.query(models.Guide)
            .filter(
                or_(
                    models.Guide.name.ilike(search_term),
                    models.Guide.description.ilike(search_term),
                )
            )
            .all()
        )
    return db.query(models.Guide).all()


# --- CREATE GUIDE (NOW SAVES SCREENSHOTS TO DISK) ---
@router.post("/", status_code=201, response_model=Guide)
async def create_guide(
    guide: GuideCreate,
    request: Request,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Create guide and save step screenshots + highlight coords.
    Accepts nested `highlight` object in each step (payload you posted).
    """
    # --- basic duplicate-check
    existing_guide = (
        db.query(models.Guide)
        .filter(models.Guide.owner_id == current_user.id, models.Guide.shortcut == guide.shortcut)
        .first()
    )
    if existing_guide:
        raise HTTPException(status_code=400, detail="A guide with this shortcut already exists.")

    try:
        db_guide = models.Guide(
            name=guide.name,
            shortcut=guide.shortcut,
            description=guide.description,
            owner_id=current_user.id,
        )
        db.add(db_guide)
        db.flush()  # so db_guide.id is available

        guide_dir = SCREENSHOT_ROOT / f"guide_{db_guide.id}"
        guide_dir.mkdir(parents=True, exist_ok=True)

        rich_steps_payload: Dict[int, Dict[str, Any]] = {}

        for i, step_data in enumerate(guide.steps):
            screenshot_path_str = None

            # Save screenshot (data URL -> file)
            raw_img = getattr(step_data, "screenshot", None)
            if raw_img:
                try:
                    if "," in raw_img:
                        _, raw_img = raw_img.split(",", 1)
                    img_bytes = base64.b64decode(raw_img)
                    img_file = guide_dir / f"step_{i+1}.png"
                    with open(img_file, "wb") as f:
                        f.write(img_bytes)
                    # Now open it with PIL
                    img = Image.open(img_file).convert("RGBA")
                    draw = ImageDraw.Draw(img, "RGBA")

                    # Extract highlight coords
                    h = getattr(step_data, "highlight", None)
                    if h:
                        x = float(h.x)
                        y = float(h.y)
                        w = float(h.width)
                        hgt = float(h.height)

                        # Draw translucent yellow rectangle
                        draw.rectangle(
                            [x, y, x + w, y + hgt],
                            fill=(255, 255, 0, 80),   # 80 alpha = translucent
                            outline=(255, 255, 0, 255),
                            width=3
                        )

                        # Save modified screenshot (overwrite original)
                        img.save(img_file)
                    screenshot_path_str = str(img_file)
                except Exception as e:
                    print(f"Error saving screenshot for step {i+1}: {e}")

            # Extract highlights:
            highlight_x = highlight_y = highlight_width = highlight_height = None

            # Case A: nested highlight object (dict or pydantic model)
            try:
                if getattr(step_data, "highlight", None):
                    h = step_data.highlight
                    if isinstance(h, dict):
                        highlight_x = h.get("x")
                        highlight_y = h.get("y")
                        highlight_width = h.get("width")
                        highlight_height = h.get("height")
                    else:
                        # pydantic model
                        highlight_x = getattr(h, "x", None)
                        highlight_y = getattr(h, "y", None)
                        highlight_width = getattr(h, "width", None)
                        highlight_height = getattr(h, "height", None)
            except Exception:
                pass

            # Case B: fallback to top-level highlight_* fields
            if highlight_x is None:
                highlight_x = getattr(step_data, "highlight_x", None)
                highlight_y = getattr(step_data, "highlight_y", None)
                highlight_width = getattr(step_data, "highlight_width", None)
                highlight_height = getattr(step_data, "highlight_height", None)

            db_step = models.Step(
                step_number=i + 1,
                selector=getattr(step_data, "selector", None),
                instruction=getattr(step_data, "instruction", None),
                screenshot_path=screenshot_path_str,
                highlight_x=highlight_x,
                highlight_y=highlight_y,
                highlight_width=highlight_width,
                highlight_height=highlight_height,
                guide_id=db_guide.id,
            )
            db.add(db_step)

            rich_steps_payload[i + 1] = {
                "action": step_data.action or None,
                "target": step_data.target or None,
            }

        db.commit()
        db.refresh(db_guide)

        # Persist rich step metadata separately (does not touch DB schema)
        try:
            rich_file = guide_dir / "rich_steps.json"
            with open(rich_file, "w", encoding="utf-8") as f:
                json.dump(rich_steps_payload, f)
        except Exception as e:
            print("Warning: failed to persist rich step metadata", e)

        # Hydrate rich fields back into response so caller gets full data immediately
        try:
            for step in db_guide.steps or []:
                payload = rich_steps_payload.get(step.step_number) or rich_steps_payload.get(
                    str(step.step_number)
                )
                if not payload:
                    continue
                if "action" in payload:
                    step.action = payload.get("action")
                if "target" in payload:
                    step.target = payload.get("target")
        except Exception as e:
            print("Warning: failed to hydrate rich step metadata into response", e)
        return db_guide

    except Exception as e:
        db.rollback()
        # Avoid concatenating objects with strings — format safely:
        raise HTTPException(status_code=400, detail=f"Error creating guide: {e}")



# --- GET MY GUIDES ---
@router.get("/", response_model=List[Guide])
async def get_user_guides(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    user = (
        db.query(models.User)
        .filter(models.User.id == current_user.id)
        .first()
    )
    guides = user.guides if user else []
    for g in guides:
        try:
            enriched = hydrate_rich_steps(g)
            if enriched:
                g.steps = enriched
        except Exception:
            continue
    return guides


def hydrate_rich_steps(guide: models.Guide):
    if not guide or not guide.id:
        return guide.steps
    guide_dir = SCREENSHOT_ROOT / f"guide_{guide.id}"
    rich_file = guide_dir / "rich_steps.json"
    if not rich_file.exists():
        return guide.steps
    try:
        with open(rich_file, "r", encoding="utf-8") as f:
            rich_map = json.load(f)
    except Exception:
        return guide.steps

    steps = guide.steps or []
    for step in steps:
        try:
            payload = rich_map.get(str(step.step_number)) or rich_map.get(step.step_number)
            if not payload:
                continue
            if "action" in payload:
                step.action = payload.get("action")
            if "target" in payload:
                step.target = payload.get("target")
        except Exception:
            continue
    return steps
