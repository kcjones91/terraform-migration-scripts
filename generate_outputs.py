#!/usr/bin/env python3
"""
=============================================================================
TERRAFORM OUTPUT GENERATOR FOR AZTFEXPORT
=============================================================================

This script parses aztfexport's main.tf and generates:
  - locals.tf: Maps resources by Azure name for easier reference
  - outputs.tf: Exposes resource maps for catalog/cross-state consumption

Usage:
    python generate_outputs.py /path/to/main.tf [--config resource_types.yaml]

Example:
    cd /infrastructure-repo/legacy-import/sub-prod-core/rg-hub-network
    python generate_outputs.py ./main.tf

Output:
    Creates locals.tf and outputs.tf in the same directory as main.tf

=============================================================================
"""

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

# Try to import yaml, fall back to embedded config if not available
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False
    print("Warning: PyYAML not installed. Using embedded configuration.")
    print("Install with: pip install pyyaml --break-system-packages")


# =============================================================================
# EMBEDDED DEFAULT CONFIGURATION (used if YAML not available)
# =============================================================================

DEFAULT_RESOURCE_TYPES = [
    # Networking
    {
        "terraform_type": "azurerm_virtual_network",
        "output_key": "vnets",
        "key_attribute": "name",
        "description": "Virtual Networks",
        "attributes": ["id", "name", "location", "resource_group_name", "address_space"]
    },
    {
        "terraform_type": "azurerm_subnet",
        "output_key": "subnets",
        "key_attribute": "composite",
        "key_template": "${virtual_network_name}/${name}",
        "description": "Subnets",
        "attributes": ["id", "name", "virtual_network_name", "resource_group_name", "address_prefixes"]
    },
    {
        "terraform_type": "azurerm_network_security_group",
        "output_key": "nsgs",
        "key_attribute": "name",
        "description": "Network Security Groups",
        "attributes": ["id", "name", "location", "resource_group_name"]
    },
    {
        "terraform_type": "azurerm_network_interface",
        "output_key": "nics",
        "key_attribute": "name",
        "description": "Network Interfaces",
        "attributes": ["id", "name", "location", "resource_group_name", "private_ip_address"]
    },
    {
        "terraform_type": "azurerm_public_ip",
        "output_key": "public_ips",
        "key_attribute": "name",
        "description": "Public IPs",
        "attributes": ["id", "name", "location", "resource_group_name", "ip_address"]
    },
    {
        "terraform_type": "azurerm_route_table",
        "output_key": "route_tables",
        "key_attribute": "name",
        "description": "Route Tables",
        "attributes": ["id", "name", "location", "resource_group_name"]
    },
    {
        "terraform_type": "azurerm_nat_gateway",
        "output_key": "nat_gateways",
        "key_attribute": "name",
        "description": "NAT Gateways",
        "attributes": ["id", "name", "location", "resource_group_name"]
    },
    # Compute
    {
        "terraform_type": "azurerm_linux_virtual_machine",
        "output_key": "linux_vms",
        "key_attribute": "name",
        "description": "Linux Virtual Machines",
        "attributes": ["id", "name", "location", "resource_group_name", "size", "private_ip_address", "admin_username"]
    },
    {
        "terraform_type": "azurerm_windows_virtual_machine",
        "output_key": "windows_vms",
        "key_attribute": "name",
        "description": "Windows Virtual Machines",
        "attributes": ["id", "name", "location", "resource_group_name", "size", "private_ip_address", "admin_username"]
    },
    {
        "terraform_type": "azurerm_virtual_machine",
        "output_key": "classic_vms",
        "key_attribute": "name",
        "description": "Classic Virtual Machines",
        "attributes": ["id", "name", "location", "resource_group_name"]
    },
    {
        "terraform_type": "azurerm_managed_disk",
        "output_key": "managed_disks",
        "key_attribute": "name",
        "description": "Managed Disks",
        "attributes": ["id", "name", "location", "resource_group_name", "storage_account_type", "disk_size_gb"]
    },
    {
        "terraform_type": "azurerm_availability_set",
        "output_key": "availability_sets",
        "key_attribute": "name",
        "description": "Availability Sets",
        "attributes": ["id", "name", "location", "resource_group_name"]
    },
    {
        "terraform_type": "azurerm_virtual_machine_scale_set",
        "output_key": "vmss",
        "key_attribute": "name",
        "description": "Virtual Machine Scale Sets",
        "attributes": ["id", "name", "location", "resource_group_name"]
    },
    # Storage
    {
        "terraform_type": "azurerm_storage_account",
        "output_key": "storage_accounts",
        "key_attribute": "name",
        "description": "Storage Accounts",
        "attributes": ["id", "name", "location", "resource_group_name", "account_tier", "account_replication_type", "primary_blob_endpoint"]
    },
    {
        "terraform_type": "azurerm_storage_container",
        "output_key": "storage_containers",
        "key_attribute": "name",
        "description": "Storage Containers",
        "attributes": ["id", "name", "storage_account_name"]
    },
    # Database
    {
        "terraform_type": "azurerm_mssql_server",
        "output_key": "sql_servers",
        "key_attribute": "name",
        "description": "Azure SQL Servers",
        "attributes": ["id", "name", "location", "resource_group_name", "fully_qualified_domain_name"]
    },
    {
        "terraform_type": "azurerm_mssql_database",
        "output_key": "sql_databases",
        "key_attribute": "name",
        "description": "Azure SQL Databases",
        "attributes": ["id", "name", "server_id"]
    },
    {
        "terraform_type": "azurerm_cosmosdb_account",
        "output_key": "cosmosdb_accounts",
        "key_attribute": "name",
        "description": "Cosmos DB Accounts",
        "attributes": ["id", "name", "location", "resource_group_name", "endpoint"]
    },
    # Identity & Security
    {
        "terraform_type": "azurerm_key_vault",
        "output_key": "key_vaults",
        "key_attribute": "name",
        "description": "Key Vaults",
        "attributes": ["id", "name", "location", "resource_group_name", "vault_uri"]
    },
    {
        "terraform_type": "azurerm_user_assigned_identity",
        "output_key": "managed_identities",
        "key_attribute": "name",
        "description": "User Assigned Managed Identities",
        "attributes": ["id", "name", "location", "resource_group_name", "client_id", "principal_id"]
    },
    # Resource Groups
    {
        "terraform_type": "azurerm_resource_group",
        "output_key": "resource_groups",
        "key_attribute": "name",
        "description": "Resource Groups",
        "attributes": ["id", "name", "location"]
    },
]


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ResourceTypeConfig:
    """Configuration for a resource type."""
    terraform_type: str
    output_key: str
    key_attribute: str
    description: str
    attributes: List[str]
    key_template: Optional[str] = None


@dataclass
class ParsedResource:
    """A parsed resource from main.tf."""
    resource_type: str
    resource_name: str  # Terraform resource name (e.g., "res-0")
    azure_name: Optional[str] = None  # Actual Azure resource name


# =============================================================================
# PARSER
# =============================================================================

class TerraformParser:
    """
    Simple parser for Terraform HCL files.
    
    Note: This is a regex-based parser that handles aztfexport output.
    For complex HCL, consider using python-hcl2 library.
    """
    
    # Pattern to match resource blocks (captures up to but NOT including the {)
    RESOURCE_PATTERN = re.compile(
        r'resource\s+"([^"]+)"\s+"([^"]+)"\s*\{',
        re.MULTILINE
    )
    
    def __init__(self, main_tf_path: str):
        self.main_tf_path = Path(main_tf_path)
        self.content = self._read_file()
        
    def _read_file(self) -> str:
        """Read the main.tf file."""
        if not self.main_tf_path.exists():
            raise FileNotFoundError(f"File not found: {self.main_tf_path}")
        return self.main_tf_path.read_text()
    
    def _extract_block_content(self, start_pos: int) -> str:
        """
        Extract the content of a resource block.
        start_pos should be right after the opening '{'.
        Returns the content between { and }.
        """
        brace_count = 1  # We're already inside the first brace
        
        for i, char in enumerate(self.content[start_pos:], start_pos):
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    return self.content[start_pos:i]
        
        return ""
    
    def _extract_top_level_attribute(self, block_content: str, attr_name: str) -> Optional[str]:
        """
        Extract a top-level attribute value from a resource block's content.
        Only matches attributes at depth 0 (not inside nested blocks).
        """
        depth = 0
        
        # Pattern to match attribute = "value"
        pattern = re.compile(rf'^\s*{attr_name}\s*=\s*"([^"]+)"')
        
        for line in block_content.split('\n'):
            # Check for attribute BEFORE updating depth (so we catch top-level attrs)
            if depth == 0:
                match = pattern.match(line)
                if match:
                    return match.group(1)
            
            # Track brace depth for this line
            depth += line.count('{') - line.count('}')
        
        return None
    
    def parse(self) -> Dict[str, List[ParsedResource]]:
        """
        Parse main.tf and return resources grouped by type.
        
        Returns:
            Dict mapping resource type to list of ParsedResource objects.
        """
        resources: Dict[str, List[ParsedResource]] = {}
        
        for match in self.RESOURCE_PATTERN.finditer(self.content):
            resource_type = match.group(1)
            resource_name = match.group(2)
            
            # Extract the resource block content (match.end() is right after the '{')
            block_content = self._extract_block_content(match.end())
            
            # Find the top-level name attribute
            azure_name = self._extract_top_level_attribute(block_content, "name")
            
            # For subnets, also get virtual_network_name
            vnet_name = None
            if resource_type == "azurerm_subnet":
                vnet_name = self._extract_top_level_attribute(block_content, "virtual_network_name")
            
            resource = ParsedResource(
                resource_type=resource_type,
                resource_name=resource_name,
                azure_name=azure_name
            )
            
            # Store vnet_name as extra data for subnet key generation
            if vnet_name:
                resource._vnet_name = vnet_name
            
            if resource_type not in resources:
                resources[resource_type] = []
            resources[resource_type].append(resource)
        
        return resources


# =============================================================================
# GENERATOR
# =============================================================================

class OutputGenerator:
    """Generates locals.tf and outputs.tf from parsed resources."""
    
    def __init__(self, resources: Dict[str, List[ParsedResource]], 
                 resource_configs: List[ResourceTypeConfig]):
        self.resources = resources
        self.config_map = {c.terraform_type: c for c in resource_configs}
    
    def generate_locals(self) -> str:
        """Generate locals.tf content."""
        lines = [
            "# =============================================================================",
            "# LOCALS - Auto-generated by generate_outputs.py",
            "# =============================================================================",
            "# This file maps aztfexport resources by their Azure names for easier reference.",
            "# DO NOT EDIT MANUALLY - regenerate using the script if main.tf changes.",
            "# =============================================================================",
            "",
            "locals {",
        ]
        
        # Track which types we actually have
        types_found = []
        
        for resource_type, resource_list in sorted(self.resources.items()):
            config = self.config_map.get(resource_type)
            if not config:
                # Unknown resource type - add a comment but skip
                lines.append(f"  # Skipped unknown type: {resource_type} ({len(resource_list)} resources)")
                continue
            
            types_found.append(config.output_key)
            
            lines.append("")
            lines.append(f"  # {config.description}")
            lines.append(f"  all_{config.output_key} = {{")
            
            for resource in resource_list:
                if not resource.azure_name:
                    lines.append(f"    # Warning: {resource.resource_name} has no name attribute")
                    continue
                
                # Generate the map key
                if config.key_attribute == "composite" and config.key_template:
                    # Handle composite keys like "vnet_name/subnet_name"
                    if hasattr(resource, '_vnet_name'):
                        key = f"{resource._vnet_name}/{resource.azure_name}"
                    else:
                        key = resource.azure_name
                else:
                    key = resource.azure_name
                
                tf_ref = f"{resource_type}.{resource.resource_name}"
                lines.append(f'    "{key}" = {tf_ref}')
            
            lines.append("  }")
        
        lines.append("}")
        lines.append("")
        
        return "\n".join(lines)
    
    def generate_outputs(self) -> str:
        """Generate outputs.tf content."""
        lines = [
            "# =============================================================================",
            "# OUTPUTS - Auto-generated by generate_outputs.py",
            "# =============================================================================",
            "# These outputs expose resources for consumption by:",
            "#   - The subscription-level catalog (merges all RG outputs)",
            "#   - Cross-state references via terraform_remote_state",
            "# DO NOT EDIT MANUALLY - regenerate using the script if main.tf changes.",
            "# =============================================================================",
            "",
        ]
        
        for resource_type, resource_list in sorted(self.resources.items()):
            config = self.config_map.get(resource_type)
            if not config:
                continue
            
            # Skip if no resources have names
            named_resources = [r for r in resource_list if r.azure_name]
            if not named_resources:
                continue
            
            lines.append(f'output "{config.output_key}" {{')
            lines.append(f'  description = "{config.description} in this resource group"')
            lines.append(f"  value = {{")
            lines.append(f"    for k, v in local.all_{config.output_key} : k => {{")
            
            # Add each attribute
            for attr in config.attributes:
                lines.append(f"      {attr} = v.{attr}")
            
            lines.append("    }")
            lines.append("  }")
            lines.append("}")
            lines.append("")
        
        # Add metadata output
        resource_types_list = ', '.join([f'"{rt}"' for rt in sorted(list(self.resources.keys()))])
        lines.extend([
            "# Metadata about this export",
            'output "_metadata" {',
            '  description = "Metadata about this legacy RG export"',
            "  value = {",
            f'    resource_count = {sum(len(r) for r in self.resources.values())}',
            f'    resource_types = [{resource_types_list}]',
            '    generated_by   = "generate_outputs.py"',
            "  }",
            "}",
            "",
        ])
        
        return "\n".join(lines)


# =============================================================================
# MAIN
# =============================================================================

def load_config(config_path: Optional[str]) -> List[ResourceTypeConfig]:
    """Load resource type configuration from YAML or use defaults."""
    if config_path and HAS_YAML and Path(config_path).exists():
        with open(config_path, 'r') as f:
            data = yaml.safe_load(f)
        
        configs = []
        for item in data.get('resource_types', []):
            configs.append(ResourceTypeConfig(
                terraform_type=item['terraform_type'],
                output_key=item['output_key'],
                key_attribute=item['key_attribute'],
                description=item.get('description', ''),
                attributes=item.get('attributes', ['id', 'name']),
                key_template=item.get('key_template')
            ))
        return configs
    else:
        # Use embedded defaults
        return [
            ResourceTypeConfig(
                terraform_type=item['terraform_type'],
                output_key=item['output_key'],
                key_attribute=item['key_attribute'],
                description=item.get('description', ''),
                attributes=item.get('attributes', ['id', 'name']),
                key_template=item.get('key_template')
            )
            for item in DEFAULT_RESOURCE_TYPES
        ]


def main():
    parser = argparse.ArgumentParser(
        description="Generate locals.tf and outputs.tf from aztfexport output",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python generate_outputs.py ./main.tf
    python generate_outputs.py /path/to/rg-folder/main.tf --config resource_types.yaml
    python generate_outputs.py ./main.tf --dry-run

The script will create locals.tf and outputs.tf in the same directory as main.tf.
        """
    )
    
    parser.add_argument(
        "main_tf",
        help="Path to main.tf generated by aztfexport"
    )
    
    parser.add_argument(
        "--config", "-c",
        help="Path to resource_types.yaml configuration file",
        default=None
    )
    
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Print output to stdout instead of writing files"
    )
    
    parser.add_argument(
        "--output-dir", "-o",
        help="Output directory (default: same as main.tf)",
        default=None
    )
    
    args = parser.parse_args()
    
    # Determine output directory
    main_tf_path = Path(args.main_tf)
    output_dir = Path(args.output_dir) if args.output_dir else main_tf_path.parent
    
    # Load configuration
    print(f"Loading resource type configuration...")
    configs = load_config(args.config)
    print(f"  Loaded {len(configs)} resource types")
    
    # Parse main.tf
    print(f"Parsing {main_tf_path}...")
    try:
        parser_obj = TerraformParser(str(main_tf_path))
        resources = parser_obj.parse()
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    
    # Print summary
    print(f"\nResources found:")
    total = 0
    for resource_type, resource_list in sorted(resources.items()):
        print(f"  {resource_type}: {len(resource_list)}")
        total += len(resource_list)
    print(f"  Total: {total}")
    
    # Generate files
    generator = OutputGenerator(resources, configs)
    locals_content = generator.generate_locals()
    outputs_content = generator.generate_outputs()
    
    if args.dry_run:
        print("\n" + "=" * 60)
        print("LOCALS.TF (dry run)")
        print("=" * 60)
        print(locals_content)
        print("\n" + "=" * 60)
        print("OUTPUTS.TF (dry run)")
        print("=" * 60)
        print(outputs_content)
    else:
        locals_path = output_dir / "locals.tf"
        outputs_path = output_dir / "outputs.tf"
        
        locals_path.write_text(locals_content)
        outputs_path.write_text(outputs_content)
        
        print(f"\nGenerated files:")
        print(f"  {locals_path}")
        print(f"  {outputs_path}")
        print("\nNext steps:")
        print("  1. Review the generated files")
        print("  2. Add backend configuration to providers.tf")
        print("  3. Run: terraform init -migrate-state")
        print("  4. Run: terraform plan (should show no changes)")


if __name__ == "__main__":
    main()
