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

    # Second-tier ML classifier (SamLowe/roberta-base-go_emotions by default).
    # The classifier elevates inbound risk to LOW when its negative-affect
    # labels cross the threshold. Capped at LOW by design — emotion
    # classification can't responsibly fabricate clinical urgency.
    enable_ml_classifier: bool = True
    ml_classifier_model: str = "SamLowe/roberta-base-go_emotions"
    # Threshold tuned empirically on go_emotions: 0.4 catches mid-strength
    # sadness/disappointment/grief signals (e.g., "feeling really down" →
    # sadness=0.42) while keeping benign greetings + joy phrases at NONE.
    # Surface in `matched_signals` lets a reviewer audit per-message.
    ml_classifier_threshold: float = 0.4
    ml_classifier_min_words: int = 4


settings = Settings()
