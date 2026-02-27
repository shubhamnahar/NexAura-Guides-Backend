# app/models.py
from sqlalchemy import Column, Integer, String, ForeignKey, Text ,Float, Boolean
from sqlalchemy.orm import relationship
from .database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    
    guides = relationship("Guide", back_populates="owner")


class Guide(Base):
    __tablename__ = "guides"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    shortcut = Column(String, index=True, unique=True, nullable=False)
    description = Column(Text, nullable=False)
    is_public = Column(Boolean, default=False)
    owner_id = Column(Integer, ForeignKey("users.id"))

    owner = relationship("User", back_populates="guides")
    steps = relationship(
        "Step",
        back_populates="guide",
        cascade="all, delete-orphan",
        order_by="Step.step_number",
    )


class Step(Base):
    __tablename__ = "steps"
    id = Column(Integer, primary_key=True, index=True)
    step_number = Column(Integer, nullable=False)
    selector = Column(Text, nullable=False)
    instruction = Column(Text, nullable=False)
    # NEW: where we store screenshot file path on disk (e.g. "guide_screenshots/guide_1/step_1.png")
    screenshot_path = Column(Text, nullable=True)

    highlight_x = Column(Float, nullable=True)
    highlight_y = Column(Float, nullable=True)
    highlight_width = Column(Float, nullable=True)
    highlight_height = Column(Float, nullable=True)

    guide_id = Column(Integer, ForeignKey("guides.id"))
    guide = relationship("Guide", back_populates="steps")
