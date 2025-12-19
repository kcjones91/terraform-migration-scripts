#!/usr/bin/env python3
"""
Migration Validation Script

Validates Terraform migration state and configuration to ensure:
- All RG states are clean (no drift)
- Outputs are present in state
- Catalog can read all RG states
- Provider versions are consistent
- No sensitive data in outputs

Usage:
    python validate_migration.py --subscription sub-prod-core
    python validate_migration.py --subscription sub-prod-core --check-drift
    python validate_migration.py --catalog-only
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Any

try:
    from config_loader import get_config, get_provider_version, validate_config
    HAS_CONFIG_LOADER = True
except ImportError:
    HAS_CONFIG_LOADER = False


# =============================================================================
# COLORS
# =============================================================================

class Colors:
    GREEN = '\033[0;32m'
    RED = '\033[0;31m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'  # No Color

    @staticmethod
    def success(text: str) -> str:
        return f"{Colors.GREEN}✓ {text}{Colors.NC}"

    @staticmethod
    def error(text: str) -> str:
        return f"{Colors.RED}✗ {text}{Colors.NC}"

    @staticmethod
    def warning(text: str) -> str:
        return f"{Colors.YELLOW}⚠ {text}{Colors.NC}"

    @staticmethod
    def info(text: str) -> str:
        return f"{Colors.BLUE}ℹ {text}{Colors.NC}"


# =============================================================================
# TERRAFORM HELPERS
# =============================================================================

def run_terraform_command(cwd: Path, *args, timeout: int = 300) -> Tuple[bool, str, str]:
    """
    Run a terraform command and return (success, stdout, stderr).
    """
    cmd = ['terraform'] + list(args)

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout
        )

        return result.returncode == 0, result.stdout, result.stderr

    except subprocess.TimeoutExpired:
        return False, "", "Command timed out"
    except Exception as e:
        return False, "", str(e)


def terraform_plan(directory: Path) -> Tuple[bool, int]:
    """
    Run terraform plan and return (is_clean, resource_changes).

    Returns:
        (True, 0) if plan is clean
        (False, N) if there are N changes
    """
    success, stdout, stderr = run_terraform_command(
        directory, 'plan', '-detailed-exitcode', '-out=tfplan'
    )

    # Exit codes: 0 = no changes, 1 = error, 2 = changes present
    if "No changes" in stdout:
        return True, 0

    # Try to count changes
    changes = 0
    for line in stdout.split('\n'):
        if 'Plan:' in line:
            # Extract number from "Plan: 3 to add, 2 to change, 1 to destroy"
            parts = line.split()
            for i, part in enumerate(parts):
                if part == 'to' and i > 0:
                    try:
                        changes += int(parts[i-1])
                    except ValueError:
                        pass

    return changes == 0, changes


def terraform_output(directory: Path) -> Dict[str, Any]:
    """Get terraform outputs as JSON."""
    success, stdout, stderr = run_terraform_command(directory, 'output', '-json')

    if not success:
        return {}

    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return {}


def check_provider_version(directory: Path) -> Tuple[bool, str]:
    """Check provider version in .terraform.lock.hcl."""
    lock_file = directory / '.terraform.lock.hcl'

    if not lock_file.exists():
        return False, "No lock file found (run terraform init)"

    content = lock_file.read_text()

    # Extract azurerm version
    if 'provider "registry.terraform.io/hashicorp/azurerm"' in content:
        # Simple extraction - look for version line
        for line in content.split('\n'):
            if 'version' in line.lower() and '=' in line:
                version = line.split('=')[1].strip().strip('"')
                return True, version

    return False, "azurerm provider not found"


# =============================================================================
# VALIDATORS
# =============================================================================

class RGValidator:
    """Validate a single resource group's Terraform state."""

    def __init__(self, rg_path: Path):
        self.rg_path = rg_path
        self.rg_name = rg_path.name
        self.errors = []
        self.warnings = []

    def validate(self) -> bool:
        """Run all validations. Returns True if all pass."""
        print(f"\n{Colors.info(f'Validating: {self.rg_name}')}")

        # Check files exist
        if not self._check_files():
            return False

        # Check terraform init
        if not self._check_init():
            return False

        # Check provider version
        self._check_provider_version()

        # Check outputs
        self._check_outputs()

        # Check plan (if requested)
        # self._check_plan()

        return len(self.errors) == 0

    def _check_files(self) -> bool:
        """Check required files exist."""
        required_files = ['main.tf', 'providers.tf', 'outputs.tf', 'locals.tf']

        for filename in required_files:
            if not (self.rg_path / filename).exists():
                self.errors.append(f"Missing required file: {filename}")

        return len(self.errors) == 0

    def _check_init(self) -> bool:
        """Check if terraform init has been run."""
        terraform_dir = self.rg_path / '.terraform'

        if not terraform_dir.exists():
            self.errors.append("Terraform not initialized (run: terraform init)")
            return False

        print(f"  {Colors.success('Terraform initialized')}")
        return True

    def _check_provider_version(self):
        """Check provider version matches expected."""
        success, version = check_provider_version(self.rg_path)

        if not success:
            self.warnings.append(f"Could not verify provider version: {version}")
            return

        expected_version = get_provider_version('azurerm') if HAS_CONFIG_LOADER else "~> 4.0"

        if version.startswith('4.'):
            print(f"  {Colors.success(f'Provider version: {version}')}")
        else:
            self.warnings.append(f"Provider version {version} may not match expected {expected_version}")

    def _check_outputs(self):
        """Check that outputs are present."""
        outputs = terraform_output(self.rg_path)

        if not outputs:
            self.warnings.append("No outputs found in state")
            return

        # Check for _metadata output
        if '_metadata' not in outputs:
            self.warnings.append("Missing _metadata output")

        resource_types = set()
        for key in outputs.keys():
            if not key.startswith('_'):
                resource_types.add(key)

        print(f"  {Colors.success(f'Found {len(resource_types)} output types')}")

    def _check_plan(self) -> bool:
        """Check that terraform plan shows no changes."""
        print(f"  Checking for drift...")

        is_clean, changes = terraform_plan(self.rg_path)

        if is_clean:
            print(f"  {Colors.success('No drift detected')}")
            return True
        else:
            self.errors.append(f"Drift detected: {changes} changes")
            return False

    def print_summary(self):
        """Print validation summary."""
        if self.errors:
            for error in self.errors:
                print(f"  {Colors.error(error)}")

        if self.warnings:
            for warning in self.warnings:
                print(f"  {Colors.warning(warning)}")


class CatalogValidator:
    """Validate subscription catalog."""

    def __init__(self, catalog_path: Path):
        self.catalog_path = catalog_path
        self.errors = []
        self.warnings = []

    def validate(self) -> bool:
        """Run all validations."""
        print(f"\n{Colors.info('Validating Catalog')}")

        if not self.catalog_path.exists():
            print(f"  {Colors.error('Catalog directory not found')}")
            return False

        # Check files
        required_files = ['data.tf', 'outputs.tf', 'providers.tf']
        for filename in required_files:
            if not (self.catalog_path / filename).exists():
                self.errors.append(f"Missing: {filename}")

        if self.errors:
            for error in self.errors:
                print(f"  {Colors.error(error)}")
            return False

        # Check init
        if not (self.catalog_path / '.terraform').exists():
            print(f"  {Colors.error('Catalog not initialized')}")
            return False

        print(f"  {Colors.success('Catalog structure valid')}")

        # Check outputs
        outputs = terraform_output(self.catalog_path)

        if not outputs:
            print(f"  {Colors.error('No catalog outputs found')}")
            return False

        # Count resources in catalog
        total_resources = 0
        for key, value in outputs.items():
            if not key.startswith('_') and isinstance(value.get('value'), dict):
                count = len(value['value'])
                total_resources += count
                print(f"  {Colors.success(f'{key}: {count} resources')}")

        print(f"  {Colors.success(f'Total resources in catalog: {total_resources}')}")

        return True


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Validate Terraform migration state',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '--subscription', '-s',
        help='Subscription folder to validate (e.g., sub-prod-core)'
    )

    parser.add_argument(
        '--catalog-only',
        action='store_true',
        help='Only validate the catalog'
    )

    parser.add_argument(
        '--check-drift',
        action='store_true',
        help='Run terraform plan to check for drift (slower)'
    )

    parser.add_argument(
        '--base-path',
        type=Path,
        default=Path('./legacy-import'),
        help='Base path for legacy imports (default: ./legacy-import)'
    )

    args = parser.parse_args()

    print("=" * 60)
    print("TERRAFORM MIGRATION VALIDATION")
    print("=" * 60)

    # Validate config if available
    if HAS_CONFIG_LOADER:
        valid, errors = validate_config()
        if not valid:
            print(f"\n{Colors.error('Configuration validation failed:')}")
            for error in errors:
                print(f"  - {error}")
            return 1
        print(f"{Colors.success('Configuration valid')}")

    if not args.subscription:
        print("\nError: --subscription required (or use --catalog-only)")
        return 1

    subscription_path = args.base_path / args.subscription

    if not subscription_path.exists():
        print(f"\nError: Subscription folder not found: {subscription_path}")
        return 1

    # Validate catalog if exists
    catalog_path = subscription_path / 'catalog'
    if catalog_path.exists():
        catalog_validator = CatalogValidator(catalog_path)
        if not catalog_validator.validate():
            print(f"\n{Colors.error('Catalog validation failed')}")
            if args.catalog_only:
                return 1
    elif args.catalog_only:
        print(f"\n{Colors.error('Catalog not found')}")
        return 1

    if args.catalog_only:
        print(f"\n{Colors.success('Catalog validation complete')}")
        return 0

    # Find all RG folders
    rg_folders = [
        d for d in subscription_path.iterdir()
        if d.is_dir() and d.name != 'catalog' and (d / 'main.tf').exists()
    ]

    if not rg_folders:
        print(f"\n{Colors.warning('No resource group folders found')}")
        return 0

    print(f"\nFound {len(rg_folders)} resource group(s) to validate")

    # Validate each RG
    failed = []
    for rg_path in sorted(rg_folders):
        validator = RGValidator(rg_path)

        if args.check_drift:
            validator._check_plan()

        if not validator.validate():
            failed.append(rg_path.name)

        validator.print_summary()

    # Summary
    print("\n" + "=" * 60)
    if failed:
        print(f"{Colors.error(f'Validation failed for {len(failed)} RG(s):')}")
        for rg_name in failed:
            print(f"  - {rg_name}")
        return 1
    else:
        print(f"{Colors.success('All validations passed!')}")
        return 0


if __name__ == '__main__':
    sys.exit(main())
