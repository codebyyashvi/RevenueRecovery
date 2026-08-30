# app/models.py
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, DateTime, Text, Boolean
from app.database import Base

class SubscriptionRiskRecord(Base):
    __tablename__ = "subscription_risk_register"

    subscription_id = Column(String, primary_key=True, index=True)
    customer_id = Column(String, index=True, default="cust_unknown")
    customer_email = Column(String, nullable=True)
    customer_contact = Column(String, nullable=True)
    plan_id = Column(String, default="plan_unknown")
    amount = Column(Float, default=0.0)
    state = Column(String)  # 'pending', 'halted', 'recovered', 'churn_risk'
    failure_reason = Column(String, default="unknown")
    retry_count = Column(Integer, default=0)
    nudges_sent = Column(Integer, default=0)
    discount_offered = Column(Boolean, default=False)
    first_failed_at = Column(DateTime, default=datetime.utcnow)
    last_action_at = Column(DateTime, nullable=True)
    is_escalated = Column(Boolean, default=False)
    resolved = Column(Boolean, default=False)

class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    subscription_id = Column(String, index=True)
    stage = Column(String)       # 'DIAGNOSIS', 'DECISION', 'EXECUTION', 'STOPPED', 'RESOLUTION'
    decision = Column(String)    # Action identifier
    reasoning_text = Column(Text)# Human-readable reasoning for judge explainability
    action_taken = Column(String)
    result = Column(String)      # 'SUCCESS', 'FAILED', 'GATED'
    timestamp = Column(DateTime, default=datetime.utcnow)

class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String, unique=True, index=True)
    event_type = Column(String)
    raw_payload = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)