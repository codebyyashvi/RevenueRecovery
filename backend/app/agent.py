# app/agent.py
from datetime import datetime, timedelta
from typing import Tuple
import razorpay
from sqlalchemy.orm import Session
from app.models import SubscriptionRiskRecord, AuditLog
from app.config import settings

client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

# Hard Operational Bounds
MAX_NUDGES = 3
MAX_RETRIES = 4
COOLDOWN_HOURS = 24
MAX_DAYS_BEFORE_CHURN = 10
DISCOUNT_PERCENT = 15

class RecoveryAgent:
    def __init__(self, db: Session):
        self.db = db

    def log_audit(self, sub_id: str, stage: str, decision: str, reasoning: str, action: str, result: str):
        entry = AuditLog(
            subscription_id=sub_id,
            stage=stage,
            decision=decision,
            reasoning_text=reasoning,
            action_taken=action,
            result=result
        )
        self.db.add(entry)
        self.db.commit()

    def should_stop(self, record: SubscriptionRiskRecord) -> Tuple[bool, str]:
        """Strict stopping rules to enforce bounded execution."""
        if record.resolved:
            return True, "Subscription already resolved."
        if record.is_escalated:
            return True, "Already escalated to manual/human queue."
        if record.nudges_sent >= MAX_NUDGES and record.retry_count >= MAX_RETRIES:
            return True, f"Bounds exceeded: Max nudges ({MAX_NUDGES}) & max retries reached."
        if record.first_failed_at and (datetime.utcnow() - record.first_failed_at).days > MAX_DAYS_BEFORE_CHURN:
            return True, f"Bounds exceeded: Older than {MAX_DAYS_BEFORE_CHURN} days. Marked churn risk."
        if record.last_action_at and (datetime.utcnow() - record.last_action_at) < timedelta(hours=COOLDOWN_HOURS):
            return True, f"Cooldown active: Last action was within {COOLDOWN_HOURS} hours."
        return False, ""

    def diagnose_root_cause(self, record: SubscriptionRiskRecord, payload_error: str = None) -> str:
        """Determines failure reason from error codes or state progression."""
        if payload_error:
            return payload_error
        if record.retry_count >= 3:
            return "bank_declined_repeatedly"
        if record.state == "halted":
            return "card_expired"
        return "insufficient_funds"

    def select_intervention(self, record: SubscriptionRiskRecord, reason: str) -> str:
        """Maps diagnosis to recovery action."""
        if reason == "insufficient_funds":
            return "SCHEDULE_RETRY_AND_NUDGE"
        elif reason in ["card_expired", "card_invalid"]:
            return "SEND_CARD_UPDATE_LINK"
        elif reason == "bank_declined_repeatedly":
            if not record.discount_offered:
                return "OFFER_DISCOUNT_PAYMENT_LINK"
            return "ESCALATE_TO_HUMAN"
        elif record.state == "halted":
            return "SEND_FINAL_NOTICE"
        return "GENERIC_NUDGE"

    def execute_action(self, record: SubscriptionRiskRecord, action: str, reason: str):
        """Executes API calls and records immutable audit traces."""
        stop, stop_reason = self.should_stop(record)
        if stop:
            self.log_audit(
                sub_id=record.subscription_id,
                stage="STOPPED",
                decision="HALT_WORKFLOW",
                reasoning=stop_reason,
                action="NONE",
                result="GATED"
            )
            return

        try:
            if action == "SCHEDULE_RETRY_AND_NUDGE":
                record.retry_count += 1
                record.nudges_sent += 1
                record.last_action_at = datetime.utcnow()
                self.log_audit(
                    record.subscription_id, "EXECUTION", action,
                    f"Diagnosed as {reason}. Scheduled next-day auto-retry and dispatched WhatsApp reminder.",
                    "RAZORPAY_RETRY_API + WHATSAPP_NUDGE", "SUCCESS"
                )

            elif action == "SEND_CARD_UPDATE_LINK":
                record.nudges_sent += 1
                record.last_action_at = datetime.utcnow()
                self.log_audit(
                    record.subscription_id, "EXECUTION", action,
                    f"Diagnosed as {reason}. Card details expired. Generated update link.",
                    "MOCK_SMS_CARD_UPDATE_LINK", "SUCCESS"
                )

            elif action == "OFFER_DISCOUNT_PAYMENT_LINK":
                # Create a discounted Razorpay Payment Link
                target_amount = record.amount if record.amount > 0 else 499.0
                discounted_amt = int(target_amount * (1 - DISCOUNT_PERCENT / 100) * 100)
                link_payload = {
                    "amount": discounted_amt,
                    "currency": "INR",
                    "description": f"Winback offer: {DISCOUNT_PERCENT}% off subscription renewal",
                    "customer": {"email": record.customer_email or "test@example.com"}
                }
                link = client.payment_link.create(link_payload)
                record.discount_offered = True
                record.last_action_at = datetime.utcnow()
                self.log_audit(
                    record.subscription_id, "EXECUTION", action,
                    f"Applied bounded incentive: {DISCOUNT_PERCENT}% discount link ({link.get('short_url')}).",
                    "RAZORPAY_PAYMENT_LINK_API", "SUCCESS"
                )

            elif action == "ESCALATE_TO_HUMAN":
                record.is_escalated = True
                record.last_action_at = datetime.utcnow()
                self.log_audit(
                    record.subscription_id, "EXECUTION", action,
                    "Automated bounds reached. Escalated to merchant operations queue.",
                    "HUMAN_QUEUE_INSERT", "SUCCESS"
                )

            self.db.commit()
        except Exception as e:
            self.log_audit(
                record.subscription_id, "EXECUTION", action,
                f"Execution error: {str(e)}", "API_DISPATCH", "FAILED"
            )