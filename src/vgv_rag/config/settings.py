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
    # GitHub App (preferred — org-level, all repos)
    github_app_id: Optional[str] = None
    github_app_private_key: Optional[str] = None  # PEM-encoded private key or path to .pem file
    github_app_installation_id: Optional[str] = None
    # GitHub PAT (fallback)
    github_pat: Optional[str] = None
    figma_api_token: Optional[str] = None
    atlassian_api_token: Optional[str] = None
    atlassian_email: Optional[str] = None
    atlassian_domain: Optional[str] = None
    google_service_account_json: Optional[str] = None  # Base64-encoded JSON key or file path

    # Voyage.ai
    voyage_api_key: str = ""  # Required — startup health check fails if empty

    # Pinecone
    pinecone_api_key: str = ""  # Required — startup health check fails if empty
    pinecone_index_name: str = "vgv-project-rag"

    # Service
    port: int = 3000
    sync_cron: str = "*/15 8-20 * * 1-5"
    log_level: str = "INFO"


settings = Settings()
