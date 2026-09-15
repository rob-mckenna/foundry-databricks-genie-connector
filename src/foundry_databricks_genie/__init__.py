"""Configuration helpers for Microsoft Foundry and Azure Databricks Genie."""

from .config import Configuration, ConfigurationError, load_configuration

__all__ = ["Configuration", "ConfigurationError", "load_configuration"]
__version__ = "0.1.0"

