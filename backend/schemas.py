from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
import datetime

# ================= AUTH SCHEMAS =================

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    role: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# ================= ORDER SCHEMAS =================

class OrderBase(BaseModel):
    customer_name: str
    customer_location: Optional[str] = None
    product_name: str
    quantity: int
    expected_delivery_date: str
    status: Optional[str] = None

    @field_validator("expected_delivery_date")
    @classmethod
    def validate_date(cls, v):
        try:
            datetime.datetime.strptime(v, "%Y-%m-%d")
        except Exception:
            raise ValueError("expected_delivery_date must be YYYY-MM-DD")
        return v


class OrderResponse(BaseModel):
    id: int
    order_number: str
    customer_name: str
    customer_location: Optional[str]
    product_name: str
    quantity: int
    expected_delivery_date: str
    status: Optional[str]
    order_date: str

    class Config:
        from_attributes = True
