from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ClinicFlow API"
    database_url: str = "postgresql+psycopg://clinicflow:clinicflow@localhost:5432/clinicflow"
    # The UI calls the API same-origin through nginx (/api), so CORS is only needed for
    # local dev servers. Override with CORS_ORIGINS='["https://clinicflow.example.com"]'.
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]
    # Opening hours of the clinic (wall-clock, clinic-local time).
    opening_hour: int = 8
    closing_hour: int = 20
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
