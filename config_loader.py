#!/usr/bin/env python3
"""
Configuration loader for Terraform migration scripts.

This module loads configuration from config.yaml and provides
easy access to settings throughout the toolkit.

Usage:
    from config_loader import get_config, get_backend_config, get_provider_version

    config = get_config()
    backend = get_backend_config()
    azurerm_version = get_provider_version('azurerm')
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False
    print("Warning: PyYAML not installed. Using default configuration.")


# =============================================================================
# DEFAULT CONFIGURATION (Fallback if YAML not available)
# =============================================================================

DEFAULT_CONFIG = {
    'terraform': {
        'required_version': '>= 1.5.0',
        'providers': {
            'azurerm': {
                'source': 'hashicorp/azurerm',
                'version': '~> 4.0'
            },
            'artifactory': {
                'source': 'jfrog/artifactory',
                'version': '~> 10.0'
            }
        }
    },
    'backend': {
        'resource_group_name': 'tfstate-rg',
        'storage_account_name': 'tfstatestore',
        'container_name': 'tfstate',
        'environment': 'public',
        'state_key_prefix': 'legacy'
    },
    'artifactory': {
        'url': 'https://artifactory.example.com',
        'backend': {
            'repo': 'terraform-state-generic',
            'subpath': 'artifactory'
        }
    },
    'discovery': {
        'max_workers': 4,
        'default_timeout': 60,
        'resource_list_timeout': 120,
        'skip_disabled_subscriptions': True,
        'folder_structure': 'flat'
    },
    'aztfexport': {
        'non_interactive': True,
        'append': False,
        'create_backup': True,
        'backup_prefix': 'raw',
        'auto_organize': True,
        'auto_split': True
    },
    'organization': {
        'resource_mapping_file': 'resource_mapping.yaml',
        'default_file': 'other.tf',
        'organized_subdir': 'organized'
    },
    'catalog': {
        'output_keys': [
            'vnets', 'subnets', 'nsgs', 'nics', 'public_ips',
            'route_tables', 'nat_gateways', 'linux_vms', 'windows_vms',
            'classic_vms', 'managed_disks', 'availability_sets', 'vmss',
            'storage_accounts', 'storage_containers', 'sql_servers',
            'sql_databases', 'cosmosdb_accounts', 'key_vaults',
            'managed_identities', 'resource_groups'
        ]
    },
    'validation': {
        'require_clean_plan': True,
        'check_provider_versions': True,
        'verify_outputs': True,
        'check_state_consistency': True,
        'max_drift_resources': 0,
        'ignore_computed_attributes': True
    },
    'logging': {
        'level': 'INFO',
        'log_file': 'migration.log',
        'show_timestamps': True,
        'colorize_output': True
    },
    'workflow': {
        'auto_apply_outputs': True,
        'require_confirmation': True,
        'max_retries': 3,
        'retry_delay': 5
    }
}


# =============================================================================
# CONFIG LOADER
# =============================================================================

_config_cache: Optional[Dict[str, Any]] = None


def get_config_path() -> Path:
    """Get the path to config.yaml."""
    # Look for config.yaml in script directory
    script_dir = Path(__file__).parent.resolve()
    config_path = script_dir / 'config.yaml'

    # Also check environment variable
    if 'TF_MIGRATION_CONFIG' in os.environ:
        config_path = Path(os.environ['TF_MIGRATION_CONFIG'])

    return config_path


def load_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load configuration from YAML file.

    Args:
        config_path: Optional path to config file. If None, uses default location.

    Returns:
        Configuration dictionary.
    """
    if config_path is None:
        config_path = get_config_path()

    if HAS_YAML and config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                # Merge with defaults to ensure all keys exist
                return merge_configs(DEFAULT_CONFIG, config)
        except Exception as e:
            print(f"Warning: Failed to load config from {config_path}: {e}")
            print("Using default configuration.")
            return DEFAULT_CONFIG
    else:
        if not HAS_YAML:
            print("PyYAML not available. Install with: pip install pyyaml")
        elif not config_path.exists():
            print(f"Config file not found: {config_path}")
        print("Using default configuration.")
        return DEFAULT_CONFIG


def merge_configs(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively merge two configuration dictionaries.
    Values in 'override' take precedence over 'base'.
    """
    result = base.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_configs(result[key], value)
        else:
            result[key] = value

    return result


def get_config(reload: bool = False) -> Dict[str, Any]:
    """
    Get the global configuration, loading it if necessary.

    Args:
        reload: Force reload from disk.

    Returns:
        Configuration dictionary.
    """
    global _config_cache

    if _config_cache is None or reload:
        _config_cache = load_config()

    return _config_cache


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_backend_config() -> Dict[str, str]:
    """Get backend configuration for Azure storage."""
    config = get_config()
    return config.get('backend', {})


def get_provider_version(provider: str) -> str:
    """
    Get version constraint for a provider.

    Args:
        provider: Provider name (e.g., 'azurerm', 'artifactory')

    Returns:
        Version constraint string (e.g., '~> 4.0')
    """
    config = get_config()
    providers = config.get('terraform', {}).get('providers', {})

    if provider in providers:
        return providers[provider].get('version', '~> 1.0')

    return '~> 1.0'


def get_provider_source(provider: str) -> str:
    """
    Get source for a provider.

    Args:
        provider: Provider name (e.g., 'azurerm', 'artifactory')

    Returns:
        Source string (e.g., 'hashicorp/azurerm')
    """
    config = get_config()
    providers = config.get('terraform', {}).get('providers', {})

    if provider in providers:
        return providers[provider].get('source', f'hashicorp/{provider}')

    return f'hashicorp/{provider}'


def get_terraform_version() -> str:
    """Get required Terraform version constraint."""
    config = get_config()
    return config.get('terraform', {}).get('required_version', '>= 1.5.0')


def get_artifactory_config() -> Dict[str, Any]:
    """Get Artifactory configuration."""
    config = get_config()
    return config.get('artifactory', {})


def get_catalog_output_keys() -> list:
    """Get list of output keys for catalog generation."""
    config = get_config()
    return config.get('catalog', {}).get('output_keys', [])


def is_azure_government() -> bool:
    """Check if configured for Azure Government."""
    backend = get_backend_config()
    env = backend.get('environment', 'public').lower()
    return env in ['usgovernment', 'government', 'gov']


def get_state_key(subscription: str, component: str) -> str:
    """
    Generate a state key based on naming convention.

    Args:
        subscription: Subscription name
        component: Component name (e.g., RG name or catalog)

    Returns:
        State key path (e.g., 'legacy/sub-prod/rg-network.tfstate')
    """
    backend = get_backend_config()
    prefix = backend.get('state_key_prefix', 'legacy')
    return f"{prefix}/{subscription}/{component}.tfstate"


# =============================================================================
# VALIDATION
# =============================================================================

def validate_config(config: Optional[Dict[str, Any]] = None) -> tuple[bool, list]:
    """
    Validate configuration.

    Args:
        config: Configuration to validate. If None, uses global config.

    Returns:
        Tuple of (is_valid, error_messages)
    """
    if config is None:
        config = get_config()

    errors = []

    # Check required sections
    required_sections = ['terraform', 'backend']
    for section in required_sections:
        if section not in config:
            errors.append(f"Missing required section: {section}")

    # Validate backend config
    backend = config.get('backend', {})
    required_backend_keys = ['resource_group_name', 'storage_account_name', 'container_name']
    for key in required_backend_keys:
        if not backend.get(key):
            errors.append(f"Missing required backend configuration: {key}")

    # Validate provider versions
    providers = config.get('terraform', {}).get('providers', {})
    if not providers:
        errors.append("No providers configured")

    return len(errors) == 0, errors


# =============================================================================
# CONFIG EXPORT
# =============================================================================

def export_config_summary() -> str:
    """Export a human-readable summary of the current configuration."""
    config = get_config()

    lines = [
        "=" * 60,
        "TERRAFORM MIGRATION CONFIGURATION",
        "=" * 60,
        "",
        "Terraform Version: " + get_terraform_version(),
        "",
        "Providers:",
    ]

    providers = config.get('terraform', {}).get('providers', {})
    for name, settings in providers.items():
        lines.append(f"  - {name}: {settings.get('source')} @ {settings.get('version')}")

    lines.extend([
        "",
        "Backend Configuration:",
        f"  Resource Group: {get_backend_config().get('resource_group_name')}",
        f"  Storage Account: {get_backend_config().get('storage_account_name')}",
        f"  Container: {get_backend_config().get('container_name')}",
        f"  Environment: {get_backend_config().get('environment')}",
        "",
        "=" * 60
    ])

    return "\n".join(lines)


# =============================================================================
# MAIN (for testing)
# =============================================================================

if __name__ == '__main__':
    print(export_config_summary())

    # Validate
    valid, errors = validate_config()
    if valid:
        print("\n✓ Configuration is valid")
    else:
        print("\n✗ Configuration has errors:")
        for error in errors:
            print(f"  - {error}")
