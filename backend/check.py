# seed_data.py
import os
import razorpay
from dotenv import load_dotenv

load_dotenv()

KEY_ID = os.getenv("RAZORPAY_KEY_ID")
KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

print("DEBUG KEY_ID:", KEY_ID)
print("DEBUG KEY_SECRET length:", len(KEY_SECRET) if KEY_SECRET else None)

client = razorpay.Client(auth=(KEY_ID, KEY_SECRET))