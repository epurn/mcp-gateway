"""Static tool registry config loader."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class ToolConfig(BaseModel):
    """Tool definition loaded from static config."""

    name: str
    description: str
    backend_url: str
    risk_level: str = "low"
    required_roles: list[str] | None = None
    is_active: bool = True
    input_schema: dict[str, Any] | None = None


class ToolRegistryConfig(BaseModel):
    """Container for tool definitions."""

    tools: list[ToolConfig] = Field(default_factory=list)


def load_tool_registry(config_path: str | None = None) -> ToolRegistryConfig:
    """Load tool registry config from YAML.

    Args:
        config_path: Optional custom path for the tool registry config.

    Returns:
        Parsed ToolRegistryConfig, or an empty config if the file is missing.
    """
    if config_path is None:
        config_path = Path(__file__).parent.parent.parent / "config" / "tools.yaml"
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        return ToolRegistryConfig()

    with config_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    return ToolRegistryConfig(**data)
