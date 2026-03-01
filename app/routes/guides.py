# app/routes/guides.py
from fastapi import APIRouter, Depends, HTTPException, status,Request,Query,BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Dict, Any
from io import BytesIO
import base64
import os
from pathlib import Path
from PIL import Image, ImageDraw
import re
import secrets
import shutil

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from .. import database, models, auth
from ..schemas import GuideCreate, Guide, GuideUpdate
import json

router = APIRouter()

# Where screenshots will be stored on disk (relative to your app root)
SCREENSHOT_ROOT = Path("guide_screenshots")

def calculate_dpr_scale(img: Image.Image, bbox: dict) -> tuple:
    """
    Calculate the correct DPR scale factor for bbox coordinates.
    
    Returns: (dpr_scale, scaled_bbox_dict)
    
    Logic:
    1. If bbox contains 'dpr' field -> use it directly
    2. If bbox contains 'cssWidth'/'cssHeight' -> calculate from ratio
    3. Otherwise assume DPR=1 (no scaling needed)
    """
    if not bbox:
        return (1.0, bbox)
    
    dpr = bbox.get('dpr')
    
    # Method 1: DPR explicitly provided
    if dpr is not None:
        dpr = float(dpr)
        scaled_bbox = {
            'x': bbox.get('x', 0),
            'y': bbox.get('y', 0),
            'width': bbox.get('width', 0),
            'height': bbox.get('height', 0),
        }
        print(f"[NexAura] Using explicit DPR: {dpr}")
        return (1.0, scaled_bbox)  # Already scaled in frontend
    
    # Method 2: Calculate DPR from CSS vs actual dimensions
    css_width = bbox.get('cssWidth')
    css_height = bbox.get('cssHeight')
    
    if css_width is not None and css_height is not None:
        img_width, img_height = img.size
        
        # Calculate DPR from width ratio
        calculated_dpr = img_width / (css_width * 2) if css_width > 0 else 1.0
        
        # Use width ratio as primary (more reliable for viewport width)
        # Standard viewport width is usually around 980-1920 CSS pixels
        # Screenshot width = viewport_width * DPR
        
        # Heuristic: if image width is significantly larger than CSS width,
        # coordinates need scaling
        if img_width > css_width * 1.5:
            dpr = img_width / (css_width * 2) if css_width > 0 else 1.0
            dpr = max(1.0, min(3.0, dpr))  # Clamp to reasonable range
            
            # Scale the coordinates
            scaled_bbox = {
                'x': bbox.get('cssX', 0) * dpr,
                'y': bbox.get('cssY', 0) * dpr,
                'width': bbox.get('cssWidth', 0) * dpr,
                'height': bbox.get('cssHeight', 0) * dpr,
            }
            print(f"[NexAura] Calculated DPR: {dpr} from image={img_width} vs css={css_width}")
            return (1.0, scaled_bbox)
    
    # Method 3: Auto-detect from image size
    # Standard screenshot sizes and their typical DPR:
    # - 1920x1080 @ DPR=1 -> 1920px wide
    # - 1920x1080 @ DPR=2 -> 3840px wide (Retina)
    img_width, img_height = img.size
    
    # Common viewport widths
    common_viewport_widths = [1920, 1680, 1440, 1366, 1280, 1024, 800]
    
    best_dpr = 1.0
    min_diff = float('inf')
    
    for vw in common_viewport_widths:
        for candidate_dpr in [1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0]:
            expected_width = vw * candidate_dpr
            diff = abs(img_width - expected_width)
            if diff < min_diff:
                min_diff = diff
                best_dpr = candidate_dpr
    
    # If we detected a high DPR, scale the bbox
    if best_dpr > 1.25:
        scaled_bbox = {
            'x': bbox.get('x', 0) * best_dpr,
            'y': bbox.get('y', 0) * best_dpr,
            'width': bbox.get('width', 0) * best_dpr,
            'height': bbox.get('height', 0) * best_dpr,
        }
        print(f"[NexAura] Auto-detected DPR: {best_dpr} from image size {img_width}x{img_height}")
        return (1.0, scaled_bbox)
    
    # No scaling needed
    print(f"[NexAura] No DPR scaling needed (DPR=1 assumed)")
    return (1.0, bbox)


def draw_highlight_on_image(img: Image.Image, bbox: dict, dpr: float = None) -> Image.Image:
    """
    Draw a translucent yellow highlight rectangle on the image.
    
    Args:
        img: PIL Image in RGBA mode
        bbox: Dict with x, y, width, height (and optionally dpr, cssX, cssY, cssWidth, cssHeight)
        dpr: Optional override for device pixel ratio
    
    Returns:
        Image with highlight overlay
    """
    if not bbox:
        return img
    
    # Get the scaled bbox
    _, scaled_bbox = calculate_dpr_scale(img, bbox)
    
    x = float(scaled_bbox.get('x', 0))
    y = float(scaled_bbox.get('y', 0))
    width = float(scaled_bbox.get('width', 0))
    height = float(scaled_bbox.get('height', 0))
    
    # Validate coordinates
    img_width, img_height = img.size
    if x < 0 or y < 0 or width <= 0 or height <= 0:
        print(f"[NexAura] WARNING: Invalid bbox coordinates: ({x}, {y}, {width}, {height})")
        return img
    
    if x > img_width or y > img_height:
        print(f"[NexAura] WARNING: Bbox outside image bounds: ({x}, {y}) vs image ({img_width}, {img_height})")
        return img
    
    # Clamp to image bounds
    x = max(0, min(x, img_width - 1))
    y = max(0, min(y, img_height - 1))
    width = min(width, img_width - x)
    height = min(height, img_height - y)
    
    print(f"[NexAura] Drawing highlight at: ({x:.2f}, {y:.2f}, {width:.2f}, {height:.2f})")
    
    # Create transparent overlay
    overlay = Image.new("RGBA", img.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)
    
    # Draw translucent yellow rectangle
    draw.rectangle(
        [x, y, x + width, y + height],
        fill=(255, 255, 0, 80),   # Yellow with 80/255 = ~31% opacity
        outline=(255, 200, 0, 200),  # Orange-yellow outline
        width=3
    )
    
    # Composite overlay onto original image
    return Image.alpha_composite(img, overlay)

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

    # 2. Ensure user has access (owner, shared, or public)
    has_access = (
        db_guide.owner_id == current_user.id or
        db_guide.is_public or
        any(access.email == current_user.email for access in db_guide.access_list)
    )
    if not has_access:
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
        # We only need to read margin_top here, so nonlocal is not strictly required
        # but the linter complains if we don't assign to it.
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
    # Use guide name for download; replace spaces with underscores and strip unsafe chars
    raw_name = (db_guide.name or f"guide-{guide_id}").strip()
    underscored = re.sub(r"\s+", "_", raw_name)
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "", underscored) or f"guide_{guide_id}"
    filename = f"{safe_name}.pdf"

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
        # 1. Store the guide_id for cleanup after commit
        guide_id_to_delete = db_guide.id

        # 2. Delete from database
        db.delete(db_guide)
        db.commit()

        # 3. Clean up screenshots on disk
        guide_dir = SCREENSHOT_ROOT / f"guide_{guide_id_to_delete}"
        if guide_dir.exists() and guide_dir.is_dir():
            shutil.rmtree(guide_dir)

    except Exception as e:
        db.rollback()
        print(f"Error deleting guide: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while deleting the guide",
        )
    return None


# --- PUBLIC SEARCH ENDPOINT ---
@router.get("/public", response_model=List[Guide])
async def search_public_guides(
    search: str = "", db: Session = Depends(database.get_db)
):
    query = db.query(models.Guide).filter(models.Guide.is_public == True)
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                models.Guide.name.ilike(search_term),
                models.Guide.description.ilike(search_term),
            )
        )
    return query.all()


# --- ACCESS CLAIM ENDPOINT ---
@router.post("/share/access/{share_token}", response_model=Guide)
async def claim_guide_access(
    share_token: str,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    db_guide = db.query(models.Guide).filter(models.Guide.share_token == share_token).first()
    if not db_guide:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invalid share token"
        )

    # Check if user already has access
    already_shared = any(access.email == current_user.email for access in db_guide.access_list)
    if not already_shared and db_guide.owner_id != current_user.id:
        # Add access
        access = models.GuideAccess(guide_id=db_guide.id, email=current_user.email)
        db.add(access)
        try:
            db.commit()
            db.refresh(db_guide)
        except Exception as e:
            db.rollback()
            print(f"Error claiming access: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An error occurred while claiming access",
            )

    # Hydrate steps and shared emails for response
    db_guide.steps = hydrate_rich_steps(db_guide)
    db_guide.shared_emails = hydrate_shared_emails(db_guide)

    return db_guide


# --- SHARE TOKEN ENDPOINT ---
@router.post("/{guide_id}/share-token", response_model=Guide)
async def generate_share_token(
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
            detail="Only the owner can generate a share token",
        )

    # Generate a unique share token
    while True:
        token = secrets.token_urlsafe(16)
        # Check if token already exists
        existing = db.query(models.Guide).filter(models.Guide.share_token == token).first()
        if not existing:
            db_guide.share_token = token
            break

    try:
        db.commit()
        db.refresh(db_guide)

        # Hydrate steps and shared emails for response
        if "rich_steps_payload" in locals() and rich_steps_payload:
            for step in db_guide.steps or []:
                payload = rich_steps_payload.get(step.step_number) or rich_steps_payload.get(str(step.step_number))
                if not payload:
                    continue
                if "action" in payload:
                    step.action = payload.get("action")
                if "target" in payload:
                    step.target = payload.get("target")
        else:
            db_guide.steps = hydrate_rich_steps(db_guide)

        db_guide.shared_emails = hydrate_shared_emails(db_guide)

        return db_guide
    except Exception as e:
        db.rollback()
        print(f"Error generating share token: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while generating the share token",
        )


# --- UPDATE ENDPOINT ---
@router.put("/{guide_id}", response_model=Guide)
async def update_guide(
    guide_id: int,
    guide_update: GuideUpdate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    db_guide = db.query(models.Guide).filter(models.Guide.id == guide_id).first()
    if not db_guide:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Guide not found"
        )

    # Check if user has edit rights (owner or shared)
    has_edit_access = (
        db_guide.owner_id == current_user.id or
        any(access.email == current_user.email for access in db_guide.access_list)
    )
    if not has_edit_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this guide",
        )

    if guide_update.name is not None:
        db_guide.name = guide_update.name
    if guide_update.shortcut is not None:
        # Check if shortcut is already taken by ANY guide
        existing = db.query(models.Guide).filter(
            models.Guide.shortcut == guide_update.shortcut,
            models.Guide.id != guide_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Shortcut already exists globally")
        db_guide.shortcut = guide_update.shortcut
    if guide_update.description is not None:
        db_guide.description = guide_update.description
    if guide_update.is_public is not None:
        # Only owner can change public status
        if db_guide.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the owner can modify public status",
            )
        db_guide.is_public = guide_update.is_public

    if guide_update.shared_emails is not None:
        # Only owner can change sharing settings
        if db_guide.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the owner can modify sharing settings",
            )
        set_guide_access(db, guide_id, guide_update.shared_emails)

    rich_steps_payload = None
    if guide_update.steps is not None:
        rich_steps_payload = process_steps_and_save_screenshots(db, db_guide, guide_update.steps)

    try:
        db.commit()
        db.refresh(db_guide)

        # Hydrate steps and shared emails for response
        if "rich_steps_payload" in locals() and rich_steps_payload:
            for step in db_guide.steps or []:
                payload = rich_steps_payload.get(step.step_number) or rich_steps_payload.get(str(step.step_number))
                if not payload:
                    continue
                if "action" in payload:
                    step.action = payload.get("action")
                if "target" in payload:
                    step.target = payload.get("target")
        else:
            db_guide.steps = hydrate_rich_steps(db_guide)

        db_guide.shared_emails = hydrate_shared_emails(db_guide)

        return db_guide
    except Exception as e:
        db.rollback()
        print(f"Error updating guide: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating the guide",
        )


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
    Extracts highlight coords from target.vision.bbox and uses alpha compositing
    to ensure the highlight is transparent and text remains visible.
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
            is_public=guide.is_public,
            owner_id=current_user.id,
        )
        db.add(db_guide)
        db.flush()  # so db_guide.id is available

        rich_steps_payload = process_steps_and_save_screenshots(db, db_guide, guide.steps)

        # Set guide access
        if guide.shared_emails:
            set_guide_access(db, db_guide.id, guide.shared_emails)

        db.commit()
        db.refresh(db_guide)

        # Hydrate rich fields
        try:
            for step in db_guide.steps or []:
                payload = rich_steps_payload.get(step.step_number) or rich_steps_payload.get(str(step.step_number))
                if not payload:
                    continue
                if "action" in payload:
                    step.action = payload.get("action")
                if "target" in payload:
                    step.target = payload.get("target")
        except Exception as e:
            print("[NexAura] Warning: failed to hydrate rich step metadata", e)

        # Hydrate shared emails for response
        db_guide.shared_emails = hydrate_shared_emails(db_guide)
            
        return db_guide

    except Exception as e:
        db.rollback()
        print(f"Error creating guide: {e}")
        raise HTTPException(status_code=400, detail="An error occurred while creating the guide")


# --- GET MY GUIDES ---
@router.get("/", response_model=List[Guide])
async def get_user_guides(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    print(f"Fetching guides for user_id={current_user.id}")
    # Return guides owned by the user OR shared with their email
    guides = (
        db.query(models.Guide)
        .outerjoin(models.GuideAccess)
        .filter(
            or_(
                models.Guide.owner_id == current_user.id,
                models.GuideAccess.email == current_user.email
            )
        )
        .distinct()
        .all()
    )

    for g in guides:
        try:
            enriched = hydrate_rich_steps(g)
            if enriched:
                g.steps = enriched
            g.shared_emails = hydrate_shared_emails(g)
        except Exception:
            continue
    print("guides--------"+str(guides))
    return guides

@router.get("/search", response_model=Guide)
async def get_guide_by_shortcut(
    shortcut: str = Query(..., description="The shortcut of the guide to find"),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    # Query database for the specific guide (owner, shared, or public)
    guide = (
        db.query(models.Guide)
        .outerjoin(models.GuideAccess)
        .filter(models.Guide.shortcut == shortcut)
        .filter(
            or_(
                models.Guide.owner_id == current_user.id,
                models.GuideAccess.email == current_user.email,
                models.Guide.is_public == True
            )
        )
        .first()
    )

    # If the guide doesn't exist, return a 404 error
    if not guide:
        raise HTTPException(status_code=404, detail="Guide not found")

    # Hydrate steps just like the main endpoint
    try:
        enriched = hydrate_rich_steps(guide)
        if enriched:
            guide.steps = enriched
        guide.shared_emails = hydrate_shared_emails(guide)
    except Exception as e:
        print(f"Error hydrating steps for specific guide: {e}")

    return guide


def set_guide_access(db: Session, guide_id: int, emails: List[str]):
    # Remove existing access
    db.query(models.GuideAccess).filter(models.GuideAccess.guide_id == guide_id).delete()

    # Add new access records
    for email in emails:
        access = models.GuideAccess(guide_id=guide_id, email=email)
        db.add(access)

def process_steps_and_save_screenshots(db: Session, db_guide: models.Guide, steps_data: List[Any]):
    # 1. Clear existing steps from DB
    db.query(models.Step).filter(models.Step.guide_id == db_guide.id).delete()

    # 2. Clear and recreate screenshot directory to avoid disk leak
    guide_dir = SCREENSHOT_ROOT / f"guide_{db_guide.id}"
    if guide_dir.exists():
        shutil.rmtree(guide_dir)
    guide_dir.mkdir(parents=True, exist_ok=True)

    rich_steps_payload: Dict[int, Dict[str, Any]] = {}

    for i, step_data in enumerate(steps_data):
        screenshot_path_str = None

        # Extract bbox from target.vision
        bbox = None
        target_data = getattr(step_data, "target", None)

        if target_data and isinstance(target_data, dict):
            vision = target_data.get("vision", {})
            bbox = vision.get("bbox")

        # Save screenshot and draw highlight
        raw_img = getattr(step_data, "screenshot", None)
        if raw_img:
            try:
                if "," in raw_img:
                    _, raw_img = raw_img.split(",", 1)
                img_bytes = base64.b64decode(raw_img)
                img_file = guide_dir / f"step_{i+1}.png"

                # Save original first
                with open(img_file, "wb") as f:
                    f.write(img_bytes)

                # Open and process
                img = Image.open(img_file).convert("RGBA")

                if bbox:
                    img = draw_highlight_on_image(img, bbox)

                # Save with highlight
                img.save(img_file, format="PNG")
                screenshot_path_str = str(img_file)

            except Exception as e:
                print(f"[NexAura] Error processing screenshot for step {i+1}: {e}")

        # Extract coordinates for DB storage
        highlight_x = float(bbox.get('x', 0)) if bbox else None
        highlight_y = float(bbox.get('y', 0)) if bbox else None
        highlight_width = float(bbox.get('width', 0)) if bbox else None
        highlight_height = float(bbox.get('height', 0)) if bbox else None

        # Save step to DB
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

    # Persist rich step metadata
    try:
        rich_file = guide_dir / "rich_steps.json"
        with open(rich_file, "w", encoding="utf-8") as f:
            json.dump(rich_steps_payload, f)
    except Exception as e:
        print("[NexAura] Warning: failed to persist rich step metadata", e)

    return rich_steps_payload

def hydrate_shared_emails(guide: models.Guide):
    if not guide:
        return []
    return [access.email for access in guide.access_list]

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
