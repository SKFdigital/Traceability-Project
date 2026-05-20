from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, validator
from typing import List, Optional
from sqlalchemy import (
    Column,
    Integer,
    String,
    Date,
    TIMESTAMP,
    func,
    create_engine,
    asc,
    desc,
    or_,
)
from fastapi import Body
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import requests
import datetime
import uuid

# ================= DATABASE =================
DATABASE_URL = "postgresql://postgres:Niraj%40242@localhost:5432/scm_db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# ================= ROUTER =================
router = APIRouter(tags=["Orders"])

# ================= DB DEPENDENCY =================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ================= SQLALCHEMY MODEL =================
class OrderDB(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    order_number = Column(String, unique=True, nullable=False)
    customer_name = Column(String, nullable=False)
    customer_location = Column(String, nullable=True)
    product_name = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    order_date = Column(Date, nullable=True)

    # REQUIRED FOR ALL-SHEETS LOGIC
    sheet_name = Column(String, nullable=False)

    expected_delivery_date = Column(Date, nullable=True)
    status = Column(String, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())

Base.metadata.create_all(bind=engine)

# ================= PYDANTIC SCHEMAS =================
class OrderBase(BaseModel):
    customer_name: str
    customer_location: Optional[str] = None
    product_name: str
    quantity: int
    expected_delivery_date: str  # YYYY-MM-DD
    status: Optional[str] = None
    sheet_name: Optional[str] = None

    @validator("expected_delivery_date")
    def validate_date(cls, v):
        try:
            datetime.datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("expected_delivery_date must be YYYY-MM-DD")
        return v

class OrderResponse(OrderBase):
    id: int
    order_number: str
    order_date: Optional[str]

    class Config:
        from_attributes = True

# ================= ADD ORDER =================
@router.post("/add_order", response_model=OrderResponse)
def add_order(order: OrderBase, db: Session = Depends(get_db)):

    delivery_date = datetime.datetime.strptime(
        order.expected_delivery_date, "%Y-%m-%d"
    ).date()

    sheet = order.sheet_name or "MANUAL"

    existing_order = db.query(OrderDB).filter(
        OrderDB.customer_name == order.customer_name,
        OrderDB.product_name == order.product_name,
        OrderDB.expected_delivery_date == delivery_date,
        OrderDB.sheet_name == sheet,
    ).first()

    if existing_order:
        raise HTTPException(status_code=409, detail="Order already exists")

    db_order = OrderDB(
        order_number=str(uuid.uuid4())[:8],
        customer_name=order.customer_name,
        customer_location=order.customer_location,
        product_name=order.product_name,
        quantity=order.quantity,
        order_date=datetime.date.today(),
        expected_delivery_date=delivery_date,
        status=order.status,
        sheet_name=sheet,
    )

    db.add(db_order)
    db.commit()
    db.refresh(db_order)

    return OrderResponse(
        id=db_order.id,
        order_number=db_order.order_number,
        customer_name=db_order.customer_name,
        customer_location=db_order.customer_location,
        product_name=db_order.product_name,
        quantity=db_order.quantity,
        expected_delivery_date=db_order.expected_delivery_date.isoformat()
        if db_order.expected_delivery_date else None,
        status=db_order.status,
        order_date=db_order.order_date.isoformat()
        if db_order.order_date else None,
        sheet_name=db_order.sheet_name,
    )

# ================= GET ORDERS =================
@router.get("/get_orders", response_model=List[OrderResponse])
def get_orders(
    search: Optional[str] = None,
    sort_by: str = "expected_delivery_date",
    order: str = "asc",
    sheet_name: Optional[str] = "ALL",
    db: Session = Depends(get_db),
):
    sort_columns = {
        "order_number": OrderDB.order_number,
        "customer_name": OrderDB.customer_name,
        "customer_location": OrderDB.customer_location,
        "product_name": OrderDB.product_name,
        "quantity": OrderDB.quantity,
        "order_date": OrderDB.order_date,
        "expected_delivery_date": OrderDB.expected_delivery_date,
        "status": OrderDB.status,
        "created_at": OrderDB.created_at,
    }

    sort_column = sort_columns.get(sort_by, OrderDB.expected_delivery_date)
    sort_func = desc if order.lower() == "desc" else asc

    query = db.query(OrderDB)

    if sheet_name != "ALL":
        query = query.filter(OrderDB.sheet_name == sheet_name)

    if search:
        query = query.filter(
            or_(
                OrderDB.order_number.ilike(f"%{search}%"),
                OrderDB.customer_name.ilike(f"%{search}%"),
                OrderDB.product_name.ilike(f"%{search}%"),
                OrderDB.status.ilike(f"%{search}%"),
            )
        )

    orders = query.order_by(sort_func(sort_column)).all()

    return [
        OrderResponse(
            id=o.id,
            order_number=o.order_number,
            customer_name=o.customer_name,
            customer_location=o.customer_location,
            product_name=o.product_name,
            quantity=o.quantity,
            expected_delivery_date=o.expected_delivery_date.isoformat()
            if o.expected_delivery_date else None,
            status=o.status,
            order_date=o.order_date.isoformat()
            if o.order_date else None,
            sheet_name=o.sheet_name,
        )
        for o in orders
    ]

# ================= IMPORT FROM GOOGLE SHEET =================

# ================= IMPORT FROM GOOGLE SHEET =================
@router.post("/import_orders_google_sheet")
def import_orders_from_google_sheet(
    sheet_name: Optional[str] = Body(default="ALL"),
    db: Session = Depends(get_db),
):
    SHEET_ID = "1J1c2u7Riv0vwhEXK3KzVXPQvxXRaHWpYdrJU9CE0FlI"

    ALL_SHEETS = [
        "Jan-26","Feb-26","Mar-26","Apr-26","May-26","Jun-26",
        "Jul-26","Aug-26","Sep-26","Oct-26","Nov-26","Dec-26",
        "Jan-27","Feb-27","Mar-27",
    ]

    sheets_to_read = ALL_SHEETS if sheet_name == "ALL" else [sheet_name]
    imported = 0

    for sheet in sheets_to_read:
        # 🧹 DELETE existing records for this sheet before reimport
        db.query(OrderDB).filter(OrderDB.sheet_name == sheet).delete()
        db.commit()

        url = f"https://opensheet.elk.sh/{SHEET_ID}/{sheet}"
        response = requests.get(url)

        if response.status_code != 200:
            continue

        rows = response.json()

        for row in rows:
            try:
                customer_name = (
                    row.get("customer_name")
                    or row.get("Customer Name")
                    or row.get("Customer")
                )

                product_name = (
                    row.get("product_name")
                    or row.get("Product")
                    or row.get("Product Name")
                )

                quantity = row.get("quantity") or row.get("Qty") or 0

                expected_delivery_date = (
                    row.get("expected_delivery_date")
                    or row.get("Delivery Date")
                    or row.get("Expected Delivery Date")
                )

                customer_location = (
                    row.get("customer_location")
                    or row.get("Location")
                    or ""
                )

                status = row.get("status") or row.get("Status") or ""

                if not customer_name or not product_name or not expected_delivery_date:
                    continue

                delivery_date = datetime.datetime.strptime(
                    expected_delivery_date, "%Y-%m-%d"
                ).date()

                db_order = OrderDB(
                    order_number=str(uuid.uuid4())[:8],
                    customer_name=customer_name,
                    customer_location=customer_location,
                    product_name=product_name,
                    quantity=int(quantity),
                    order_date=datetime.date.today(),
                    expected_delivery_date=delivery_date,
                    status=status,
                    sheet_name=sheet,
                )

                db.add(db_order)
                imported += 1

            except Exception as e:
                print("Skipped row:", row, e)

    db.commit()

    return {
        "message": f"Imported {imported} orders",
        "sheet": sheet_name,
    }



# ================= GET SHEET NAMES =================

@router.get("/get_sheet_names")
def get_sheet_names():
    # Generate months dynamically from Jan-26 through Mar-29
    start_year = 2026
    end_year = 2029
    months = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
    ]

    sheets = []
    for year in range(start_year, end_year + 1):
        for m in months:
            sheets.append(f"{m}-{str(year)[-2:]}")

    return ["ALL"] + sheets



# ================= UPDATE ORDER =================
@router.put("/update_order/{order_id}", response_model=OrderResponse)
def update_order(order_id: int, order: OrderBase, db: Session = Depends(get_db)):
    db_order = db.query(OrderDB).filter(OrderDB.id == order_id).first()
    if not db_order:
        raise HTTPException(status_code=404, detail="Order not found")

    db_order.customer_name = order.customer_name
    db_order.customer_location = order.customer_location
    db_order.product_name = order.product_name
    db_order.quantity = order.quantity
    db_order.expected_delivery_date = datetime.datetime.strptime(
        order.expected_delivery_date, "%Y-%m-%d"
    ).date()
    db_order.status = order.status

    if order.sheet_name:
        db_order.sheet_name = order.sheet_name

    db.commit()
    db.refresh(db_order)

    return OrderResponse(
        id=db_order.id,
        order_number=db_order.order_number,
        customer_name=db_order.customer_name,
        customer_location=db_order.customer_location,
        product_name=db_order.product_name,
        quantity=db_order.quantity,
        expected_delivery_date=db_order.expected_delivery_date.isoformat()
        if db_order.expected_delivery_date else None,
        status=db_order.status,
        order_date=db_order.order_date.isoformat()
        if db_order.order_date else None,
        sheet_name=db_order.sheet_name,
    )

# ================= DELETE ORDER =================
@router.delete("/delete_order/{order_id}")
def delete_order(order_id: int, db: Session = Depends(get_db)):
    db_order = db.query(OrderDB).filter(OrderDB.id == order_id).first()
    if not db_order:
        raise HTTPException(status_code=404, detail="Order not found")

    db.delete(db_order)
    db.commit()
    return {"message": "Order deleted successfully"}
