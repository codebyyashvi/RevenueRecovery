# app/main.py
import json
from fastapi import FastAPI, Request, HTTPException, Depends, Header
from sqlalchemy.orm import Session
import razorpay
import datetime

from app.database import get_db, engine, Base
from app.models import SubscriptionRiskRecord, WebhookEvent, AuditLog
from app.agent import RecoveryAgent
from app.config import settings

Base.metadata.create_all(bind=engine)
app = FastAPI(title="Razorpay AI Revenue Recovery Engine")
client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

@app.get("/")
def root():
    return {"status": "active", "service": "Razorpay Revenue Recovery Agent"}

@app.post("/webhooks/razorpay")
async def handle_razorpay_webhook(
    request: Request,
    x_razorpay_signature: str = Header(None),
    db: Session = Depends(get_db)
):
    body = await request.body()
    body_str = body.decode("utf-8")

    # Verify signature if signature header is present
    if x_razorpay_signature:
        try:
            client.utility.verify_webhook_signature(body_str, x_razorpay_signature, settings.RAZORPAY_WEBHOOK_SECRET)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Razorpay webhook signature")

    payload = json.loads(body_str)
    event_type = payload.get("event")
    event_id = payload.get("account_id", "acc") + "_" + str(payload.get("created_at", datetime.utcnow().timestamp()))

    # Deduplicate events
    if not db.query(WebhookEvent).filter_by(event_id=event_id).first():
        db.add(WebhookEvent(event_id=event_id, event_type=event_type, raw_payload=body_str))
        db.commit()

    agent = RecoveryAgent(db)

    # Process failure and recovery events
    if event_type in ["subscription.pending", "subscription.halted"]:
        sub_data = payload.get("payload", {}).get("subscription", {}).get("entity", {})
        sub_id = sub_data.get("id")
        
        record = db.query(SubscriptionRiskRecord).filter_by(subscription_id=sub_id).first()
        if not record:
            record = SubscriptionRiskRecord(
                subscription_id=sub_id,
                customer_id=sub_data.get("customer_id", "cust_unknown"),
                plan_id=sub_data.get("plan_id", "plan_unknown"),
                amount=499.0,
                state=sub_data.get("status")
            )
            db.add(record)
            db.commit()
        else:
            record.state = sub_data.get("status")
            db.commit()

        reason = agent.diagnose_root_cause(record)
        action = agent.select_intervention(record, reason)
        agent.execute_action(record, action, reason)

    elif event_type == "subscription.charged":
        sub_id = payload.get("payload", {}).get("subscription", {}).get("entity", {}).get("id")
        record = db.query(SubscriptionRiskRecord).filter_by(subscription_id=sub_id).first()
        if record:
            record.resolved = True
            record.state = "recovered"
            db.commit()
            agent.log_audit(sub_id, "RESOLUTION", "MARKED_RECOVERED", "Payment charged successfully.", "CLEAR_RISK", "SUCCESS")

    return {"status": "processed", "event": event_type}

@app.post("/agent/run-batch")
def run_batch_recovery(db: Session = Depends(get_db)):
    """Runs recovery interventions over all unresolved subscriptions."""
    at_risk = db.query(SubscriptionRiskRecord).filter(SubscriptionRiskRecord.resolved == False).all()
    agent = RecoveryAgent(db)
    
    results = []
    for record in at_risk:
        reason = agent.diagnose_root_cause(record)
        action = agent.select_intervention(record, reason)
        agent.execute_action(record, action, reason)
        results.append({
            "subscription_id": record.subscription_id,
            "reason": reason,
            "action": action,
            "state": record.state
        })

    return {"processed_count": len(results), "actions": results}

@app.get("/agent/risk-register")
def get_risk_register(db: Session = Depends(get_db)):
    return db.query(SubscriptionRiskRecord).all()

@app.get("/agent/audit-logs")
def get_audit_logs(db: Session = Depends(get_db)):
    return db.query(AuditLog).order_by(AuditLog.id.desc()).limit(100).all()

@app.get("/agent/metrics")
def get_metrics(db: Session = Depends(get_db)):
    total = db.query(SubscriptionRiskRecord).all()
    recovered = [r for r in total if r.resolved]
    total_val = sum(r.amount for r in total)
    recovered_val = sum(r.amount for r in recovered)
    escalated = [r for r in total if r.is_escalated]

    return {
        "total_at_risk_amount": total_val,
        "total_recovered_amount": recovered_val,
        "recovery_rate_pct": round((recovered_val / total_val * 100), 2) if total_val > 0 else 0,
        "total_at_risk_count": len(total),
        "recovered_count": len(recovered),
        "escalated_count": len(escalated)
    }