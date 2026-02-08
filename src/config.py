from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    # App
    APP_NAME: str = "MCP Gateway"
    DEBUG: bool = False
    
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://mcp_user:mcp_password@localhost:5432/mcp_gateway"
    
    # Security
    JWT_SECRET_KEY: str = "change_me_in_production_please_super_secret"
    JWT_ALGORITHM: str = "HS256"
    JWT_ALLOWED_ALGORITHMS: str = "HS256"
    JWT_MAX_TOKEN_AGE_MINUTES: int = 60
    JWT_CLOCK_SKEW_SECONDS: int = 60
    JWT_USER_ID_CLAIM: str = "sub"
    JWT_EXP_CLAIM: str = "exp"
    JWT_IAT_CLAIM: str = "iat"
    JWT_TENANT_CLAIM: str = "workspace"
    JWT_API_VERSION_CLAIM: str = "v"
    JWT_ALLOWED_API_VERSIONS: str = ""
    TOOL_GATEWAY_SHARED_SECRET: str = ""
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_ISSUER: str = ""
    JWT_AUDIENCE: str = ""
    
    # MCP
    MCP_LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

@lru_cache()
def get_settings() -> Settings:
    return Settings()
