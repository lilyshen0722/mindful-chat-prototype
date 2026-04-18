from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Mindful Chat Prototype"

    openrouter_api_key: str = ""
    openrouter_model: str = "meta-llama/llama-3.2-3b-instruct:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    admin_username: str = "admin"
    admin_password: str = "change-me-locally"

    database_path: str = "./data/app.db"
    log_level: str = "INFO"


settings = Settings()
