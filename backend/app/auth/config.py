from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthSettings(BaseSettings):
    auth_trusted_proxies: str = ""
    app_env: str = "production"
    auth_cookie_secure: bool = True
    auth_session_seconds: int = Field(28800, ge=60, le=86400)
    auth_allowed_origins: str = (
        "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:8080,http://localhost:8080"
    )
    model_config = SettingsConfigDict(extra="ignore")

    @model_validator(mode="after")
    def secure_defaults(self):
        if not self.auth_cookie_secure and self.app_env != "development":
            raise ValueError("Insecure cookies require APP_ENV=development")
        from ipaddress import ip_network

        for cidr in self.auth_trusted_proxies.split(","):
            if cidr.strip():
                ip_network(cidr.strip(), strict=False)
        return self

    @property
    def origins(self):
        return {value.strip().rstrip("/") for value in self.auth_allowed_origins.split(",") if value.strip()}
