from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6379/0"

    ANTHROPIC_API_KEY: str
    VAPI_API_KEY: str
    VAPI_PHONE_NUMBER_ID: str = ""
    VAPI_ASSISTANT_ID: str = ""
    VAPI_WEBHOOK_SECRET: str = ""

    TWILIO_ACCOUNT_SID: str
    TWILIO_AUTH_TOKEN: str
    TWILIO_PHONE_NUMBER: str

    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    S3_BUCKET: str = "wayco-pi-documents"

    DROPBOX_SIGN_API_KEY: str = ""

    SECRET_KEY: str = "change-me-in-production"
    APP_URL: str = "http://localhost:8000"
    ENVIRONMENT: str = "development"

    FIRM_NAME: str = "Smith & Associates Law Firm"
    FIRM_ADDRESS: str = "123 Legal Blvd, Los Angeles, CA 90001"
    FIRM_PHONE: str = "+1-213-555-0100"
    FIRM_EMAIL: str = "intake@smithlaw.com"
    FIRM_BAR_NUMBER: str = "CA-123456"

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
