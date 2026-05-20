from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey
from datetime import datetime
from database import Base

# -------------------- USERS --------------------
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)


# -------------------- ORDERS --------------------
class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    order_number = Column(String, unique=True, nullable=False)
    customer_name = Column(String, nullable=False)
    product_name = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    order_date = Column(Date, nullable=False)
    expected_delivery_date = Column(Date, nullable=True)
    status = Column(String, default="Pending")
    created_at = Column(DateTime, default=datetime.utcnow)

# -------------------- INVENTORY --------------------
class Inventory(Base):
    __tablename__ = "inventory"
    id = Column(Integer, primary_key=True, index=True)
    item_code = Column(String, unique=True, nullable=False)
    item_name = Column(String, nullable=False)
    category = Column(String, nullable=True)
    quantity_available = Column(Integer, default=0)
    reorder_level = Column(Integer, default=0)
    warehouse_location = Column(String, nullable=True)
    last_updated = Column(DateTime, default=datetime.utcnow)

# -------------------- PRODUCTION PLAN --------------------
class ProductionPlan(Base):
    __tablename__ = "production_plan"
    id = Column(Integer, primary_key=True, index=True)
    product_name = Column(String, nullable=False)
    planned_quantity = Column(Integer, nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    status = Column(String, default="Planned")
    created_at = Column(DateTime, default=datetime.utcnow)

# -------------------- PROCUREMENT --------------------
class Procurement(Base):
    __tablename__ = "procurement"
    id = Column(Integer, primary_key=True, index=True)
    item_name = Column(String, nullable=False)
    required_quantity = Column(Integer, nullable=False)
    vendor_id = Column(Integer, ForeignKey("vendors.id"))
    order_date = Column(Date, nullable=False)
    expected_arrival = Column(Date, nullable=True)
    status = Column(String, default="Pending")

# -------------------- VENDORS --------------------
class Vendor(Base):
    __tablename__ = "vendors"
    id = Column(Integer, primary_key=True, index=True)
    vendor_name = Column(String, nullable=False)
    contact_person = Column(String, nullable=True)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    rating = Column(Float, default=0.0)
    active_status = Column(Integer, default=1)

# -------------------- FINANCE TRANSACTIONS --------------------
class FinanceTransaction(Base):
    __tablename__ = "finance_transactions"
    id = Column(Integer, primary_key=True, index=True)
    reference_type = Column(String)  # e.g., Order, Procurement
    reference_id = Column(Integer)
    amount = Column(Float, nullable=False)
    transaction_type = Column(String)  # Credit / Debit
    payment_status = Column(String, default="Pending")
    transaction_date = Column(DateTime, default=datetime.utcnow)

# -------------------- LOGISTICS --------------------
class Logistics(Base):
    __tablename__ = "logistics"
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    transport_mode = Column(String, nullable=True)
    route_details = Column(String, nullable=True)
    dispatch_date = Column(Date, nullable=True)
    delivery_date = Column(Date, nullable=True)
    status = Column(String, default="Pending")

# -------------------- CHATBOT LOGS --------------------
class ChatbotLog(Base):
    __tablename__ = "chatbot_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_query = Column(String, nullable=False)
    bot_response = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
