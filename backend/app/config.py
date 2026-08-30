# app/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    RAZORPAY_KEY_ID: str
    RAZORPAY_KEY_SECRET: str
    RAZORPAY_WEBHOOK_SECRET: str
    DATABASE_URL: str = "sqlite:///./recovery_agent.db"

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()