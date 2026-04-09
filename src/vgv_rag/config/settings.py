from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Required
    supabase_url: str
    supabase_service_role_key: str
    supabase_anon_key: str

    # Optional connectors
    notion_api_token: Optional[str] = None
    slack_bot_token: Optional[str] = None
    github_pat: Optional[str] = None
    figma_api_token: Optional[str] = None
    atlassian_api_token: Optional[str] = None
    atlassian_email: Optional[str] = None
    atlassian_domain: Optional[str] = None
    google_service_account_json: Optional[str] = None  # Base64-encoded JSON key or file path

    # Service
    port: int = 3000
    sync_cron: str = "*/15 8-20 * * 1-5"
    log_level: str = "INFO"


settings = Settings()
