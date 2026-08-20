"""HFSG - Hospital Flow Scenario Generator.

Phase 1 MVP package.
"""

from .config import Configuration, ConfigurationLoader, ConfigError

__all__ = ["Configuration", "ConfigurationLoader", "ConfigError"]
__version__ = "0.1.0"