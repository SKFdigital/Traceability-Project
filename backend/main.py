from fastapi import FastAPI, Depends, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from datetime import datetime

# ---------- INTERNAL IMPORTS ----------
from database import Base, engine, SessionLocal
from models import (
    User, Inventory, ProductionPlan, Vendor, Procurement,
    FinanceTransaction, Logistics, ChatbotLog,
)
from auth import hash_password, verify_password, create_token
from schemas import RegisterRequest, LoginRequest
from order_backend_postgres import router as order_router

# ================= APP =================
app = FastAPI(title="AI-Driven SCM Backend API")

# ================= CORS =================
# Using a wide-open policy to eliminate connection errors while you debug
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================= DATABASE =================
Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ================= AUTHENTICATION ROUTES =================
@app.post("/register")
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == data.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=data.email,
        password_hash=hash_password(data.password), # Matches your models
        role=data.role,
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"message": "User registered successfully", "user_id": user.id}

@app.post("/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    # Ensure you are checking the hashed password field
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_token({"email": user.email, "role": user.role})
    return {"access_token": token, "token_type": "bearer", "role": user.role}

# ================= INCLUDE ROUTERS =================
app.include_router(order_router)

# ================= OTHER ROUTES (Kept intact) =================
@app.get("/")
def root():
    return {"message": "SCM Backend Running"}

@app.get("/users")
def list_users(db: Session = Depends(get_db)):
    return db.query(User).all()



# ================= REGISTER =================
@app.post("/register")
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == data.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        role=data.role,
        is_active=1,
        created_at=datetime.utcnow(),
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return {"message": "User registered successfully", "user_id": user.id}

# ================= LOGIN =================
@app.post("/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()

    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_token({"email": user.email, "role": user.role})
    return {"token": token, "role": user.role}

# ================= USERS (DEBUG) =================
@app.get("/users")
def list_users(db: Session = Depends(get_db)):
    users = db.query(User).all()
    return [{"id": u.id, "email": u.email, "role": u.role} for u in users]

# ============================================================
# 🔥 INCLUDE ORDERS ROUTER (THIS IS WHAT FIXES 404s)
# ============================================================
app.include_router(order_router)

# ================= PROCUREMENT =================
@app.get("/procurement")
def get_procurements(db: Session = Depends(get_db)):
    return db.query(Procurement).all()

@app.post("/procurement")
def create_procurement(proc: dict = Body(...), db: Session = Depends(get_db)):
    new_proc = Procurement(
        item_name=proc.get("item_name"),
        required_quantity=proc.get("required_quantity"),
        vendor_id=proc.get("vendor_id"),
        order_date=proc.get("order_date"),
        expected_arrival=proc.get("expected_arrival"),
        status=proc.get("status", "Pending"),
    )
    db.add(new_proc)
    db.commit()
    db.refresh(new_proc)
    return {"message": "Procurement created", "procurement_id": new_proc.id}

# ================= INVENTORY =================
@app.get("/inventory")
def get_inventory(db: Session = Depends(get_db)):
    return db.query(Inventory).all()

@app.post("/inventory")
def create_inventory(item: dict = Body(...), db: Session = Depends(get_db)):
    new_item = Inventory(
        item_code=item.get("item_code"),
        item_name=item.get("item_name"),
        category=item.get("category"),
        quantity_available=item.get("quantity_available", 0),
        reorder_level=item.get("reorder_level", 0),
        warehouse_location=item.get("warehouse_location"),
    )
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    return {"message": "Inventory item added", "inventory_id": new_item.id}

# ================= PRODUCTION =================
@app.get("/production_plan")
def get_production_plans(db: Session = Depends(get_db)):
    return db.query(ProductionPlan).all()

@app.post("/production_plan")
def create_production_plan(plan: dict = Body(...), db: Session = Depends(get_db)):
    new_plan = ProductionPlan(
        product_name=plan.get("product_name"),
        planned_quantity=plan.get("planned_quantity"),
        start_date=plan.get("start_date"),
        end_date=plan.get("end_date"),
        status=plan.get("status", "Planned"),
    )
    db.add(new_plan)
    db.commit()
    db.refresh(new_plan)
    return {"message": "Production plan created", "plan_id": new_plan.id}

# ================= VENDORS =================
@app.get("/vendors")
def get_vendors(db: Session = Depends(get_db)):
    return db.query(Vendor).all()

@app.post("/vendors")
def create_vendor(vendor: dict = Body(...), db: Session = Depends(get_db)):
    new_vendor = Vendor(
        vendor_name=vendor.get("vendor_name"),
        contact_person=vendor.get("contact_person"),
        email=vendor.get("email"),
        phone=vendor.get("phone"),
        rating=vendor.get("rating", 0),
    )
    db.add(new_vendor)
    db.commit()
    db.refresh(new_vendor)
    return {"message": "Vendor added", "vendor_id": new_vendor.id}

# ================= FINANCE =================
@app.get("/finance")
def get_finance(db: Session = Depends(get_db)):
    return db.query(FinanceTransaction).all()

@app.post("/finance")
def create_finance(txn: dict = Body(...), db: Session = Depends(get_db)):
    new_txn = FinanceTransaction(
        reference_type=txn.get("reference_type"),
        reference_id=txn.get("reference_id"),
        amount=txn.get("amount"),
        transaction_type=txn.get("transaction_type"),
        payment_status=txn.get("payment_status", "Pending"),
    )
    db.add(new_txn)
    db.commit()
    db.refresh(new_txn)
    return {"message": "Transaction recorded", "transaction_id": new_txn.id}

# ================= LOGISTICS =================
@app.get("/logistics")
def get_logistics(db: Session = Depends(get_db)):
    return db.query(Logistics).all()

@app.post("/logistics")
def create_logistics(log: dict = Body(...), db: Session = Depends(get_db)):
    new_log = Logistics(
        order_id=log.get("order_id"),
        transport_mode=log.get("transport_mode"),
        route_details=log.get("route_details"),
        dispatch_date=log.get("dispatch_date"),
        delivery_date=log.get("delivery_date"),
        status=log.get("status", "Pending"),
    )
    db.add(new_log)
    db.commit()
    db.refresh(new_log)
    return {"message": "Logistics record created", "logistics_id": new_log.id}

# ================= CHATBOT LOGS =================
@app.get("/chatbot_logs")
def get_chatbot_logs(db: Session = Depends(get_db)):
    return db.query(ChatbotLog).all()

@app.post("/chatbot_logs")
def create_chatbot_log(log: dict = Body(...), db: Session = Depends(get_db)):
    new_log = ChatbotLog(
        user_query=log.get("user_query"),
        bot_response=log.get("bot_response"),
    )
    db.add(new_log)
    db.commit()
    db.refresh(new_log)
    return {"message": "Chatbot log added", "chatbot_log_id": new_log.id}
