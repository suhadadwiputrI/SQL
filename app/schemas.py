from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime


# ─── Item Schemas ─────────────────────────────────────────────────────────────

class ItemBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200, example="Laptop Gaming")
    description: Optional[str] = Field(None, example="Laptop untuk keperluan gaming")
    price: float = Field(default=0.0, ge=0, example=15000000.0)
    is_available: bool = Field(default=True)


class ItemCreate(ItemBase):
    pass


class ItemUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    price: Optional[float] = Field(None, ge=0)
    is_available: Optional[bool] = None


class ItemOut(ItemBase):
    id: int
    owner_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ─── User Schemas ─────────────────────────────────────────────────────────────

class UserBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, example="Budi Santoso")
    email: EmailStr = Field(..., example="budi@example.com")


class UserCreate(UserBase):
    password: str = Field(..., min_length=6, example="password123")


class UserUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = None


class UserOut(UserBase):
    id: int
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    items: List[ItemOut] = []

    class Config:
        from_attributes = True
