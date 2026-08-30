# seed_data.py
import os
import razorpay
from dotenv import load_dotenv
from app.database import SessionLocal, engine, Base
from app.models import SubscriptionRiskRecord

load_dotenv()
Base.metadata.create_all(bind=engine)

KEY_ID = os.getenv("RAZORPAY_KEY_ID")
KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")
client = razorpay.Client(auth=(KEY_ID, KEY_SECRET))

def seed():
    db = SessionLocal()
    print("1. Creating Monthly Plan in Razorpay...")
    plan = client.plan.create({
        "period": "monthly",
        "interval": 1,
        "item": {
            "name": "Standard SaaS Subscription",
            "amount": 49900,
            "currency": "INR",
            "description": "₹499/mo Plan"
        }
    })
    plan_id = plan["id"]
    print(f"Plan ID: {plan_id}")

    test_users = [
        {"name": "Aarav Sharma", "email": "aarav@test.com", "state": "pending", "reason": "insufficient_funds"},
        {"name": "Neha Patel", "email": "neha@test.com", "state": "halted", "reason": "card_expired"},
        {"name": "Rohan Verma", "email": "rohan@test.com", "state": "pending", "reason": "bank_declined_repeatedly"},
        {"name": "Pooja Mehta", "email": "pooja@test.com", "state": "pending", "reason": "insufficient_funds"},
        {"name": "Vikram Singh", "email": "vikram@test.com", "state": "halted", "reason": "card_expired"},
    ]

    print("\n2. Creating Subscriptions and populating Risk Register...")
    for user in test_users:
        sub = client.subscription.create({
            "plan_id": plan_id,
            "total_count": 12,
            "quantity": 1,
            "customer_notify": 1,
            "notes": {"name": user["name"], "email": user["email"]}
        })
        
        record = SubscriptionRiskRecord(
            subscription_id=sub["id"],
            customer_email=user["email"],
            plan_id=plan_id,
            amount=499.0,
            state=user["state"],
            failure_reason=user["reason"]
        )
        db.merge(record)
        print(f"Added {user['name']} -> {sub['id']} ({user['state']})")

    db.commit()
    db.close()
    print("\nSeeding complete!")

if __name__ == "__main__":
    seed()