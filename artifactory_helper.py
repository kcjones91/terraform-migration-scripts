#!/usr/bin/env python3
"""
Artifactory Helper Script

This script helps manage JFrog Artifactory resources and integrates
with the Terraform migration workflow.

Features:
- Discover existing Artifactory repositories
- Generate Terraform configuration for Artifactory resources
- Validate Artifactory connectivity
- Sync state between Azure and Artifactory backends

Usage:
    python artifactory_helper.py discover --url https://artifactory.example.com
    python artifactory_helper.py generate --url https://artifactory.example.com
    python artifactory_helper.py validate

Prerequisites:
    - requests library: pip install requests
    - ARTIFACTORY_ACCESS_TOKEN environment variable set
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    print("Warning: 'requests' library not installed.")
    print("Install with: pip install requests")

try:
    from config_loader import get_artifactory_config
    HAS_CONFIG_LOADER = True
except ImportError:
    HAS_CONFIG_LOADER = False


# =============================================================================
# ARTIFACTORY API CLIENT
# =============================================================================

class ArtifactoryClient:
    """Simple Artifactory API client."""

    def __init__(self, url: str, access_token: Optional[str] = None):
        self.url = url.rstrip('/')
        self.access_token = access_token or os.getenv('ARTIFACTORY_ACCESS_TOKEN')

        if not self.access_token:
            raise ValueError(
                "Artifactory access token not provided. "
                "Set ARTIFACTORY_ACCESS_TOKEN environment variable."
            )

        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        })

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict:
        """Make an API request to Artifactory."""
        url = f"{self.url}/artifactory/api/{endpoint}"

        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json() if response.content else {}
        except requests.exceptions.RequestException as e:
            print(f"API request failed: {e}")
            return {'error': str(e)}

    def ping(self) -> bool:
        """Test connectivity to Artifactory."""
        try:
            response = self.session.get(f"{self.url}/artifactory/api/system/ping")
            return response.status_code == 200 and response.text.strip() == 'OK'
        except Exception:
            return False

    def get_repositories(self) -> List[Dict]:
        """Get list of all repositories."""
        result = self._make_request('GET', 'repositories')
        return result if isinstance(result, list) else []

    def get_repository(self, repo_key: str) -> Dict:
        """Get details of a specific repository."""
        return self._make_request('GET', f'repositories/{repo_key}')

    def get_users(self) -> List[Dict]:
        """Get list of users."""
        result = self._make_request('GET', 'security/users')
        return result if isinstance(result, list) else []

    def get_groups(self) -> List[Dict]:
        """Get list of groups."""
        result = self._make_request('GET', 'security/groups')
        return result if isinstance(result, list) else []

    def get_permissions(self) -> List[Dict]:
        """Get list of permission targets."""
        result = self._make_request('GET', 'security/permissions')
        return result if isinstance(result, list) else []


# =============================================================================
# TERRAFORM GENERATOR
# =============================================================================

class ArtifactoryTerraformGenerator:
    """Generate Terraform configuration for Artifactory resources."""

    def __init__(self, client: ArtifactoryClient):
        self.client = client

    def generate_repository_resource(self, repo: Dict) -> str:
        """Generate Terraform resource for a repository."""
        repo_key = repo.get('key', '')
        repo_type = repo.get('type', 'local').lower()
        package_type = repo.get('packageType', 'generic').lower()

        # Sanitize resource name
        resource_name = repo_key.replace('-', '_').replace('.', '_')

        lines = [
            f'resource "artifactory_{repo_type}_repository" "{resource_name}" {{',
            f'  key          = "{repo_key}"',
            f'  package_type = "{package_type}"',
        ]

        # Add optional attributes based on repo details
        full_repo = self.client.get_repository(repo_key)

        if 'description' in full_repo:
            lines.append(f'  description  = "{full_repo["description"]}"')

        if 'notes' in full_repo:
            lines.append(f'  notes        = "{full_repo["notes"]}"')

        lines.append('}')
        lines.append('')

        return '\n'.join(lines)

    def generate_all_repositories(self) -> str:
        """Generate Terraform configuration for all repositories."""
        repos = self.client.get_repositories()

        if not repos:
            return "# No repositories found\n"

        lines = [
            "# =============================================================================",
            "# Artifactory Repositories - Auto-generated",
            "# =============================================================================",
            "",
        ]

        for repo in repos:
            lines.append(self.generate_repository_resource(repo))

        return '\n'.join(lines)


# =============================================================================
# COMMANDS
# =============================================================================

def cmd_discover(args):
    """Discover Artifactory resources."""
    if not HAS_REQUESTS:
        print("Error: 'requests' library required for this command")
        return 1

    url = args.url or (get_artifactory_config().get('url') if HAS_CONFIG_LOADER else None)
    if not url:
        print("Error: Artifactory URL not provided and not found in config")
        return 1

    print(f"Connecting to: {url}")

    try:
        client = ArtifactoryClient(url)

        # Test connectivity
        if not client.ping():
            print("Error: Unable to connect to Artifactory")
            return 1

        print("✓ Connected successfully\n")

        # Discover repositories
        print("Discovering repositories...")
        repos = client.get_repositories()
        print(f"Found {len(repos)} repositories:\n")

        for repo in repos:
            print(f"  - {repo.get('key')} ({repo.get('type')}, {repo.get('packageType')})")

        # Discover users
        print("\nDiscovering users...")
        users = client.get_users()
        print(f"Found {len(users)} users")

        # Discover groups
        print("\nDiscovering groups...")
        groups = client.get_groups()
        print(f"Found {len(groups)} groups")

        # Save inventory
        if args.output:
            inventory = {
                'url': url,
                'repositories': repos,
                'users': users,
                'groups': groups
            }

            output_path = Path(args.output)
            with open(output_path, 'w') as f:
                json.dump(inventory, f, indent=2)

            print(f"\n✓ Inventory saved to: {output_path}")

        return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_generate(args):
    """Generate Terraform configuration."""
    if not HAS_REQUESTS:
        print("Error: 'requests' library required for this command")
        return 1

    url = args.url or (get_artifactory_config().get('url') if HAS_CONFIG_LOADER else None)
    if not url:
        print("Error: Artifactory URL not provided and not found in config")
        return 1

    try:
        client = ArtifactoryClient(url)

        if not client.ping():
            print("Error: Unable to connect to Artifactory")
            return 1

        generator = ArtifactoryTerraformGenerator(client)
        tf_config = generator.generate_all_repositories()

        if args.output:
            output_path = Path(args.output)
            output_path.write_text(tf_config)
            print(f"✓ Generated Terraform configuration: {output_path}")
        else:
            print(tf_config)

        return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_validate(args):
    """Validate Artifactory configuration."""
    if HAS_CONFIG_LOADER:
        config = get_artifactory_config()
        url = config.get('url')
    else:
        url = os.getenv('ARTIFACTORY_URL')

    if not url:
        print("Error: Artifactory URL not configured")
        print("Set ARTIFACTORY_URL environment variable or configure in config.yaml")
        return 1

    print(f"Validating connection to: {url}")

    if not HAS_REQUESTS:
        print("Warning: 'requests' library not available - cannot test connection")
        return 1

    try:
        client = ArtifactoryClient(url)

        if client.ping():
            print("✓ Connection successful")
            return 0
        else:
            print("✗ Connection failed")
            return 1

    except Exception as e:
        print(f"✗ Validation failed: {e}")
        return 1


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Artifactory helper for Terraform migration',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Discover resources
    python artifactory_helper.py discover --url https://artifactory.example.com

    # Generate Terraform config
    python artifactory_helper.py generate --url https://artifactory.example.com -o repos.tf

    # Validate connection
    python artifactory_helper.py validate

Environment Variables:
    ARTIFACTORY_ACCESS_TOKEN  - Access token for authentication (required)
    ARTIFACTORY_URL           - Artifactory instance URL (optional if in config)
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    # Discover command
    discover_parser = subparsers.add_parser('discover', help='Discover Artifactory resources')
    discover_parser.add_argument('--url', help='Artifactory instance URL')
    discover_parser.add_argument('--output', '-o', help='Save inventory to JSON file')

    # Generate command
    generate_parser = subparsers.add_parser('generate', help='Generate Terraform configuration')
    generate_parser.add_argument('--url', help='Artifactory instance URL')
    generate_parser.add_argument('--output', '-o', help='Output file (default: stdout)')

    # Validate command
    validate_parser = subparsers.add_parser('validate', help='Validate Artifactory connection')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    if args.command == 'discover':
        return cmd_discover(args)
    elif args.command == 'generate':
        return cmd_generate(args)
    elif args.command == 'validate':
        return cmd_validate(args)

    return 0


if __name__ == '__main__':
    sys.exit(main())
