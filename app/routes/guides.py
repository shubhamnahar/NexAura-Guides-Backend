# app/routes/guides.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List
from io import BytesIO
import base64
import os
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from .. import database, models, auth
from ..schemas import GuideCreate, Guide

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
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    existing_guide = (
        db.query(models.Guide)
        .filter(
            models.Guide.owner_id == current_user.id,
            models.Guide.shortcut == guide.shortcut,
        )
        .first()
    )
    if existing_guide:
        raise HTTPException(
            status_code=400, detail="A guide with this shortcut already exists."
        )

    try:
        db_guide = models.Guide(
            name=guide.name,
            shortcut=guide.shortcut,
            description=guide.description,
            owner_id=current_user.id,
        )
        db.add(db_guide)
        db.flush()  # get db_guide.id

        # Ensure root dir exists
        SCREENSHOT_ROOT.mkdir(parents=True, exist_ok=True)
        guide_dir = SCREENSHOT_ROOT / f"guide_{db_guide.id}"
        guide_dir.mkdir(parents=True, exist_ok=True)

        for i, step_data in enumerate(guide.steps):
            screenshot_path_str = None

            if step_data.screenshot:
                try:
                    raw = step_data.screenshot
                    # handle data URL "data:image/png;base64,...."
                    if "," in raw:
                        _, raw = raw.split(",", 1)
                    img_bytes = base64.b64decode(raw)
                    img_file = guide_dir / f"step_{i+1}.png"
                    with open(img_file, "wb") as f:
                        f.write(img_bytes)
                    screenshot_path_str = str(img_file)
                except Exception as e:
                    # Don't break guide creation if screenshot fails
                    print("Error saving screenshot:", e)

            db_step = models.Step(
                step_number=i + 1,
                selector=step_data.selector,
                instruction=step_data.instruction,
                screenshot_path=screenshot_path_str,
                guide_id=db_guide.id,
            )
            db.add(db_step)

        db.commit()
        db.refresh(db_guide)
        return db_guide

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Error creating guide: {e}")


# --- GET MY GUIDES ---
@router.get("/", response_model=List[Guide])
async def get_user_guides(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    return (
        db.query(models.User)
        .filter(models.User.id == current_user.id)
        .first()
        .guides
    )
