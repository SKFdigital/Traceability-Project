from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey
from datetime import datetime
from database import Base

# =======================================================
#               EXISTING MODELS (Unchanged)
# =======================================================

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)

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

class ProductionPlan(Base):
    __tablename__ = "production_plan"
    id = Column(Integer, primary_key=True, index=True)
    product_name = Column(String, nullable=False)
    planned_quantity = Column(Integer, nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    status = Column(String, default="Planned")
    created_at = Column(DateTime, default=datetime.utcnow)

class Procurement(Base):
    __tablename__ = "procurement"
    id = Column(Integer, primary_key=True, index=True)
    item_name = Column(String, nullable=False)
    required_quantity = Column(Integer, nullable=False)
    vendor_id = Column(Integer, ForeignKey("vendors.id"))
    order_date = Column(Date, nullable=False)
    expected_arrival = Column(Date, nullable=True)
    status = Column(String, default="Pending")

class Vendor(Base):
    __tablename__ = "vendors"
    id = Column(Integer, primary_key=True, index=True)
    vendor_name = Column(String, nullable=False)
    contact_person = Column(String, nullable=True)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    rating = Column(Float, default=0.0)
    active_status = Column(Integer, default=1)

class FinanceTransaction(Base):
    __tablename__ = "finance_transactions"
    id = Column(Integer, primary_key=True, index=True)
    reference_type = Column(String)
    reference_id = Column(Integer)
    amount = Column(Float, nullable=False)
    transaction_type = Column(String)
    payment_status = Column(String, default="Pending")
    transaction_date = Column(DateTime, default=datetime.utcnow)

class Logistics(Base):
    __tablename__ = "logistics"
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    transport_mode = Column(String, nullable=True)
    route_details = Column(String, nullable=True)
    dispatch_date = Column(Date, nullable=True)
    delivery_date = Column(Date, nullable=True)
    status = Column(String, default="Pending")

class ChatbotLog(Base):
    __tablename__ = "chatbot_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_query = Column(String, nullable=False)
    bot_response = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

# =======================================================
#               TRACEABILITY MODULE MODELS
# =======================================================

class JobWorkReport(Base):
    __tablename__ = 'jobwork_report'
    id = Column(Integer, primary_key=True, index=True)
    sr_no = Column(Integer)
    company_code = Column(String)
    system_manual_challan = Column(String)
    challan_type = Column(String)
    month = Column(String)
    year = Column(Integer)
    gstin_jw = Column(String)
    job_worker = Column(String)
    jw_challan_no = Column(String, unique=True)
    jw_challan_date = Column(Date)
    mo_number = Column(String, index=True)
    product_code = Column(String)
    hsn_code = Column(String)
    uqc = Column(String)
    qty_sent = Column(Float)
    unit_rate = Column(Float)
    taxable_value = Column(Float)
    gst_rate = Column(Float)
    gst = Column(Float)
    last_challan_date = Column(Date, nullable=True)
    qty_approved = Column(Float)
    qty_returned = Column(Float)
    returned_weight = Column(Float)
    difference_balance_qty = Column(Float)
    mat_recd_within_days = Column(Integer, nullable=True)
    current_status = Column(String)
    user_name = Column(String)
    normalized_mo = Column(String, index=True) 

class TRBMaster(Base):
    __tablename__ = 'trb_master'
    id = Column(Integer, primary_key=True, index=True)
    sheet_name = Column(String)
    mo_type = Column(String)
    pc_qty = Column(String)
    tag_type = Column(String)
    packaging_details = Column(String)
    date = Column(Date, index=True)
    shift = Column(Integer)
    production = Column(Float)
    cumulative_production = Column(Float)
    remark = Column(String)
    end_buffer = Column(Float)
    towards_packaging = Column(Float)
    next_station = Column(String)
    qty1 = Column(Float)
    qty2 = Column(Float)
    qty3 = Column(Float)
    normalized_mo = Column(String, index=True)

class DGBBMaster(Base):
    __tablename__ = 'dgbb_master'
    id = Column(Integer, primary_key=True, index=True)
    sheet_name = Column(String)
    mo_type = Column(String)
    pc_qty = Column(String)
    tag_type = Column(String)
    packaging_details = Column(String)
    date = Column(Date, index=True)
    shift = Column(Integer)
    production = Column(Float)
    cumulative_production = Column(Float)
    remark = Column(String)
    end_buffer = Column(Float)
    towards_packaging = Column(Float)
    next_station = Column(String)
    qty1 = Column(Float)
    qty2 = Column(Float)
    qty3 = Column(Float)
    normalized_mo = Column(String, index=True)

class TraceabilityMaster(Base):
    __tablename__ = 'traceability_master'
    id = Column(Integer, primary_key=True, index=True)
    source_channel = Column(String)
    mo_type = Column(String)
    pc_qty = Column(String)
    tag_type = Column(String)
    packaging_details = Column(String)
    date = Column(Date)
    shift = Column(Integer)
    production = Column(Float)
    cumulative_production = Column(Float)
    remark = Column(String)
    end_buffer = Column(Float)
    towards_packaging = Column(Float)
    next_station = Column(String)
    qty1 = Column(Float)
    qty2 = Column(Float)
    qty3 = Column(Float)
    normalized_mo = Column(String, index=True)

class TraceabilityLog(Base):
    __tablename__ = 'traceability_log'
    id = Column(Integer, primary_key=True, index=True)
    normalized_mo = Column(String, index=True)
    sync_date = Column(DateTime, default=datetime.utcnow)
    reconciliation_details = Column(String) # Store JSON or summary of match
    status = Column(String) # e.g., 'Matched', 'Pending Audit'
