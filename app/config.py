from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


def get_settings() -> Settings:
    return Settings()