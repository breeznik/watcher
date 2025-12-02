from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Watcher"
    secret_key: str = Field(default="change-me")
    database_url: str = Field(default="sqlite:///./data/data.db")
    admin_username: str = Field(default="admin")
    admin_password: str = Field(default="admin123")
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_tls: bool = True
    from_email: str | None = None
    timezone: str = "UTC"
    render_js: bool = False
    render_timeout: int = 20  # seconds
    render_post_wait_seconds: int = 3  # extra wait after DOMContentLoaded
    # Debug/diagnostics options
    debug_dump_artifacts: bool = False  # when true, save fetched HTML and screenshots
    debug_artifacts_dir: str = "./data/artifacts"  # where to save debug files
    debug_wait_selector: str | None = None  # optional CSS selector to wait for when rendering

def get_settings() -> Settings:
    return Settings()