# app/schemas.py
from pydantic import BaseModel
from typing import List, Optional

# --- Steps ---

# Data coming FROM the extension when creating a guide
class StepCreate(BaseModel):
    selector: str
    instruction: str
    # base64 PNG (will be optional)
    screenshot: Optional[str] = None


# Data going TO the frontend when fetching guides
class Step(BaseModel):
    id: int
    step_number: int
    guide_id: int
    selector: str
    instruction: str
    # we expose path as-is for now; you can later convert to URL if you want
    screenshot_path: Optional[str] = None

    class Config:
        from_attributes = True


# --- Guides ---

class GuideBase(BaseModel):
    name: str
    shortcut: str
    description: str

class GuideCreate(GuideBase):
    steps: List[StepCreate]

class Guide(GuideBase):
    id: int
    owner_id: int
    steps: List[Step] = []

    class Config:
        from_attributes = True


# --- Users ---

class UserCreate(BaseModel):
    email: str
    password: str

class User(BaseModel):
    id: int
    email: str
    guides: List[Guide] = []

    class Config:
        from_attributes = True
