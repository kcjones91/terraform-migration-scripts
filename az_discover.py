#!/usr/bin/env python3
"""
az_discover.py - Discover Azure subscriptions and resource groups, create folder structure

This script:
1. Enumerates all subscriptions you have access to
2. Lists resource groups in each subscription
3. Counts resources per RG
4. Generates a folder structure for Terraform
5. Creates a manifest file for tracking progress

Prerequisites:
    - Azure CLI installed and logged in (az login)
    - For Azure Government: az cloud set --name AzureUSGovernment

Usage:
    python az_discover.py                      # Discover and show inventory
    python az_discover.py --create-structure   # Create folder structure
    python az_discover.py --output inventory.json  # Save to JSON
    python az_discover.py --subscription-filter "prod-*"  # Filter subs

Cross-platform: Works on Windows and Linux
"""

import json
import subprocess
import sys
import argparse
import re
from pathlib import Path
from datetime import datetime
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed


def run_az_command(args: list, timeout: int = 60) -> dict:
    """Run an Azure CLI command and return JSON output."""
    cmd = ['az'] + args + ['--output', 'json']
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=(sys.platform == 'win32')  # shell=True needed on Windows for az.cmd
        )
        
        if result.returncode != 0:
            error_msg = result.stderr.strip() if result.stderr else 'Unknown error'
            return {'error': error_msg, 'success': False}
        
        if result.stdout.strip():
            return {'data': json.loads(result.stdout), 'success': True}
        return {'data': [], 'success': True}
        
    except subprocess.TimeoutExpired:
        return {'error': 'Command timed out', 'success': False}
    except json.JSONDecodeError as e:
        return {'error': f'JSON parse error: {e}', 'success': False}
    except FileNotFoundError:
        return {'error': 'Azure CLI not found. Install from https://aka.ms/installazurecli', 'success': False}


def get_current_cloud() -> str:
    """Get the current Azure cloud environment."""
    result = run_az_command(['cloud', 'show'])
    if result['success']:
        return result['data'].get('name', 'Unknown')
    return 'Unknown'


def get_subscriptions(name_filter: Optional[str] = None) -> list:
    """Get list of subscriptions."""
    result = run_az_command(['account', 'list', '--all'])
    
    if not result['success']:
        print(f"Error getting subscriptions: {result['error']}")
        return []
    
    subs = result['data']
    
    # Apply filter if provided
    if name_filter:
        pattern = name_filter.replace('*', '.*')
        subs = [s for s in subs if re.match(pattern, s.get('name', ''), re.IGNORECASE)]
    
    return subs


def get_resource_groups(subscription_id: str) -> list:
    """Get resource groups for a subscription."""
    result = run_az_command([
        'group', 'list',
        '--subscription', subscription_id
    ])
    
    if not result['success']:
        return []
    
    return result['data']


def get_resources_in_rg(subscription_id: str, rg_name: str) -> list:
    """Get resources in a resource group."""
    result = run_az_command([
        'resource', 'list',
        '--subscription', subscription_id,
        '--resource-group', rg_name
    ], timeout=120)
    
    if not result['success']:
        return []
    
    return result['data']


def count_resources_by_type(resources: list) -> dict:
    """Count resources by type."""
    counts = {}
    for r in resources:
        rtype = r.get('type', 'Unknown')
        counts[rtype] = counts.get(rtype, 0) + 1
    return counts


def discover_subscription(sub: dict, include_resources: bool = False) -> dict:
    """Discover resource groups and optionally resources for a subscription."""
    sub_id = sub['id']
    sub_name = sub['name']
    
    print(f"  Discovering: {sub_name}...", end=' ', flush=True)
    
    rgs = get_resource_groups(sub_id)
    
    sub_info = {
        'id': sub_id,
        'name': sub_name,
        'state': sub.get('state', 'Unknown'),
        'tenant_id': sub.get('tenantId', ''),
        'resource_groups': []
    }
    
    total_resources = 0
    
    for rg in rgs:
        rg_info = {
            'name': rg['name'],
            'location': rg.get('location', 'Unknown'),
            'resource_count': 0,
            'resource_types': {}
        }
        
        if include_resources:
            resources = get_resources_in_rg(sub_id, rg['name'])
            rg_info['resource_count'] = len(resources)
            rg_info['resource_types'] = count_resources_by_type(resources)
            total_resources += len(resources)
        
        sub_info['resource_groups'].append(rg_info)
    
    print(f"{len(rgs)} RGs, {total_resources} resources")
    
    return sub_info


def create_folder_structure(inventory: dict, base_path: Path, structure_type: str = 'flat') -> list:
    """
    Create folder structure based on inventory.
    
    structure_type:
        'flat' - subscriptions/sub-name/rg-name/
        'hierarchical' - environments/sub-name/resource-groups/rg-name/
    """
    created_dirs = []
    
    for sub in inventory['subscriptions']:
        # Sanitize subscription name for folder
        sub_folder = sanitize_name(sub['name'])
        
        if structure_type == 'flat':
            sub_path = base_path / 'subscriptions' / sub_folder
        else:
            sub_path = base_path / 'environments' / sub_folder
        
        # Create subscription-level files
        sub_path.mkdir(parents=True, exist_ok=True)
        created_dirs.append(sub_path)
        
        # Create placeholder files
        create_subscription_files(sub_path, sub, inventory['cloud'])
        
        # Create RG folders
        for rg in sub['resource_groups']:
            rg_folder = sanitize_name(rg['name'])
            rg_path = sub_path / rg_folder
            rg_path.mkdir(parents=True, exist_ok=True)
            created_dirs.append(rg_path)
            
            # Create placeholder for RG
            create_rg_readme(rg_path, rg, sub)
    
    return created_dirs


def sanitize_name(name: str) -> str:
    """Sanitize a name for use as a folder name."""
    # Replace spaces and special chars with hyphens
    sanitized = re.sub(r'[^\w\-]', '-', name.lower())
    # Remove consecutive hyphens
    sanitized = re.sub(r'-+', '-', sanitized)
    # Remove leading/trailing hyphens
    return sanitized.strip('-')


def create_subscription_files(path: Path, sub: dict, cloud: str):
    """Create starter Terraform files for a subscription."""
    
    # Determine environment setting
    env_setting = ''
    if 'government' in cloud.lower():
        env_setting = '\n  environment = "usgovernment"'
    
    # backend.tf
    backend_content = f'''# Backend configuration for {sub['name']}
# Uncomment and configure for remote state

# terraform {{
#   backend "azurerm" {{
#     resource_group_name  = "rg-terraform-state"
#     storage_account_name = "stterraformstate"
#     container_name       = "tfstate"
#     key                  = "{sanitize_name(sub['name'])}.tfstate"
#   }}
# }}
'''
    (path / 'backend.tf').write_text(backend_content)
    
    # providers.tf
    providers_content = f'''# Provider configuration for {sub['name']}
# Subscription ID: {sub['id']}

terraform {{
  required_providers {{
    azurerm = {{
      source  = "hashicorp/azurerm"
      version = "~> 3.0"  # Update to latest stable
    }}
  }}
  required_version = ">= 1.5.0"
}}

provider "azurerm" {{
  features {{}}{env_setting}
  subscription_id = "{sub['id']}"
}}
'''
    (path / 'providers.tf').write_text(providers_content)
    
    # README.md
    readme_content = f'''# {sub['name']}

**Subscription ID:** `{sub['id']}`  
**State:** {sub.get('state', 'Unknown')}  
**Tenant ID:** `{sub.get('tenant_id', '')}`

## Resource Groups

| Name | Location | Resources |
|------|----------|-----------|
'''
    for rg in sub['resource_groups']:
        readme_content += f"| {rg['name']} | {rg['location']} | {rg.get('resource_count', '?')} |\n"
    
    readme_content += '''
## Import Progress

- [ ] aztfexport completed
- [ ] Files organized
- [ ] terraform plan clean
- [ ] Code review done
'''
    (path / 'README.md').write_text(readme_content)


def create_rg_readme(path: Path, rg: dict, sub: dict):
    """Create a README for a resource group folder."""
    content = f'''# {rg['name']}

**Subscription:** {sub['name']}  
**Location:** {rg['location']}  
**Resource Count:** {rg.get('resource_count', 'Unknown')}

## Resource Types

'''
    if rg.get('resource_types'):
        for rtype, count in sorted(rg['resource_types'].items()):
            content += f"- {rtype}: {count}\n"
    else:
        content += "_Run discovery with --include-resources to see resource types_\n"
    
    content += '''
## Import Instructions

```bash
# Navigate to this directory
cd {path}

# Run aztfexport for this resource group
aztfexport resource-group {rg_name} --output-dir .

# Split the generated main.tf
python ../../../tf_splitter.py main.tf .

# Validate
terraform init
terraform plan
```

## Status

- [ ] Exported
- [ ] Split & organized
- [ ] Plan clean
- [ ] Reviewed
'''.format(path=path, rg_name=rg['name'])
    
    (path / 'README.md').write_text(content)


def save_inventory(inventory: dict, output_path: Path):
    """Save inventory to JSON file."""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(inventory, f, indent=2)
    print(f"\nInventory saved to: {output_path}")


def print_summary(inventory: dict):
    """Print a summary of the inventory."""
    print("\n" + "=" * 60)
    print("AZURE INVENTORY SUMMARY")
    print("=" * 60)
    print(f"Cloud: {inventory['cloud']}")
    print(f"Discovered: {inventory['discovered_at']}")
    print(f"Total Subscriptions: {len(inventory['subscriptions'])}")
    
    total_rgs = sum(len(s['resource_groups']) for s in inventory['subscriptions'])
    total_resources = sum(
        sum(rg.get('resource_count', 0) for rg in s['resource_groups'])
        for s in inventory['subscriptions']
    )
    
    print(f"Total Resource Groups: {total_rgs}")
    print(f"Total Resources: {total_resources}")
    print()
    
    print("Subscriptions:")
    for sub in sorted(inventory['subscriptions'], key=lambda x: x['name']):
        rg_count = len(sub['resource_groups'])
        res_count = sum(rg.get('resource_count', 0) for rg in sub['resource_groups'])
        print(f"  {sub['name']}: {rg_count} RGs, {res_count} resources")


def main():
    parser = argparse.ArgumentParser(
        description='Discover Azure subscriptions and resource groups',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python az_discover.py
    python az_discover.py --include-resources
    python az_discover.py --create-structure --base-path ./terraform
    python az_discover.py --subscription-filter "prod-*"
    python az_discover.py --output inventory.json
        """
    )
    
    parser.add_argument('--include-resources', '-r', action='store_true',
                        help='Include resource counts per RG (slower)')
    parser.add_argument('--create-structure', '-c', action='store_true',
                        help='Create folder structure')
    parser.add_argument('--base-path', '-b', type=Path, default=Path('./terraform'),
                        help='Base path for folder structure (default: ./terraform)')
    parser.add_argument('--output', '-o', type=Path,
                        help='Save inventory to JSON file')
    parser.add_argument('--subscription-filter', '-f', type=str,
                        help='Filter subscriptions by name pattern (supports * wildcard)')
    parser.add_argument('--parallel', '-p', type=int, default=4,
                        help='Number of parallel subscription discoveries (default: 4)')
    
    args = parser.parse_args()
    
    # Check Azure CLI login
    print("Checking Azure CLI authentication...")
    cloud = get_current_cloud()
    print(f"Cloud environment: {cloud}")
    
    if cloud == 'Unknown':
        print("\nError: Not logged in to Azure CLI.")
        print("Run: az login")
        print("For Azure Government: az cloud set --name AzureUSGovernment && az login")
        sys.exit(1)
    
    # Get subscriptions
    print("\nFetching subscriptions...")
    subs = get_subscriptions(args.subscription_filter)
    
    if not subs:
        print("No subscriptions found.")
        sys.exit(1)
    
    print(f"Found {len(subs)} subscriptions")
    
    # Discover each subscription
    print("\nDiscovering resource groups...")
    
    inventory = {
        'cloud': cloud,
        'discovered_at': datetime.now().isoformat(),
        'subscriptions': []
    }
    
    # Sequential discovery (parallel can hit rate limits)
    for sub in subs:
        if sub.get('state') != 'Enabled':
            print(f"  Skipping disabled subscription: {sub['name']}")
            continue
        
        sub_info = discover_subscription(sub, include_resources=args.include_resources)
        inventory['subscriptions'].append(sub_info)
    
    # Print summary
    print_summary(inventory)
    
    # Save to file
    if args.output:
        save_inventory(inventory, args.output)
    
    # Create folder structure
    if args.create_structure:
        print(f"\nCreating folder structure in: {args.base_path}")
        created = create_folder_structure(inventory, args.base_path)
        print(f"Created {len(created)} directories")
        
        # Copy toolkit files
        toolkit_source = get_script_dir()
        toolkit_dest = args.base_path / 'toolkit'
        toolkit_dest.mkdir(parents=True, exist_ok=True)
        
        print(f"\nCopy the toolkit files to: {toolkit_dest}")
        print("  - tf_splitter.py")
        print("  - config/resource_mapping.yaml")
        print("  - az_export_rg.py (export helper)")


if __name__ == '__main__':
    main()
