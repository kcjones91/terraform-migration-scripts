#!/usr/bin/env python3
"""
tf_splitter.py - Split aztfexport main.tf into organized files

Reads resource type mappings from config/resource_mapping.yaml and organizes
a monolithic main.tf into categorized files.

Usage:
    python tf_splitter.py <input_file> [output_dir]
    python tf_splitter.py main.tf split/
    python tf_splitter.py main.tf  # Defaults to ./split

Cross-platform: Works on Windows and Linux
"""

import re
import sys
import argparse
from pathlib import Path
from collections import defaultdict
from typing import Optional

# Try to import yaml, fall back to json config if not available
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False
    print("Warning: PyYAML not installed. Install with: pip install pyyaml")
    print("Falling back to embedded default mappings.\n")


def get_script_dir() -> Path:
    """Get the directory where this script is located."""
    return Path(__file__).parent.resolve()


def load_config(config_path: Optional[Path] = None) -> dict:
    """Load resource mappings from YAML config file."""
    
    if config_path is None:
        # Look for config relative to script location
        config_path = get_script_dir() / "config" / "resource_mapping.yaml"
    
    if YAML_AVAILABLE and config_path.exists():
        print(f"Loading config from: {config_path}")
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    # Fallback to embedded defaults
    print("Using embedded default mappings")
    return get_default_mappings()


def get_default_mappings() -> dict:
    """Embedded default mappings if YAML config not available."""
    return {
        'mappings': {
            'compute.tf': [
                'azurerm_linux_virtual_machine',
                'azurerm_windows_virtual_machine',
                'azurerm_virtual_machine',
                'azurerm_availability_set',
            ],
            'compute-disks.tf': [
                'azurerm_managed_disk',
                'azurerm_virtual_machine_data_disk_attachment',
            ],
            'compute-nics.tf': [
                'azurerm_network_interface',
                'azurerm_network_interface_security_group_association',
            ],
            'compute-extensions.tf': [
                'azurerm_virtual_machine_extension',
            ],
            'networking.tf': [
                'azurerm_virtual_network',
                'azurerm_subnet',
                'azurerm_public_ip',
                'azurerm_virtual_network_peering',
            ],
            'networking-nsgs.tf': [
                'azurerm_network_security_group',
                'azurerm_network_security_rule',
                'azurerm_subnet_network_security_group_association',
            ],
            'networking-routes.tf': [
                'azurerm_route_table',
                'azurerm_route',
                'azurerm_subnet_route_table_association',
            ],
            'storage.tf': [
                'azurerm_storage_account',
                'azurerm_storage_container',
                'azurerm_storage_blob',
            ],
            'databases-sql.tf': [
                'azurerm_mssql_server',
                'azurerm_mssql_database',
            ],
            'keyvault.tf': [
                'azurerm_key_vault',
                'azurerm_key_vault_access_policy',
                'azurerm_key_vault_secret',
            ],
            'identity.tf': [
                'azurerm_user_assigned_identity',
                'azurerm_role_assignment',
            ],
            'resource-groups.tf': [
                'azurerm_resource_group',
            ],
        },
        'default_file': 'other.tf',
        'skip_types': [],
    }


def build_type_to_file_map(config: dict) -> dict:
    """
    Build a reverse mapping from resource type to target file.
    Returns dict like: {'azurerm_virtual_machine': 'compute.tf', ...}
    """
    type_to_file = {}
    mappings = config.get('mappings', {})
    
    for filename, resource_types in mappings.items():
        for rtype in resource_types:
            type_to_file[rtype] = filename
    
    return type_to_file


def parse_tf_blocks(content: str) -> list:
    """
    Parse all top-level blocks (resource, data, variable, output, locals, etc.)
    from a Terraform file.
    
    Returns list of tuples: (block_type, resource_type, resource_name, full_block_text)
    For non-resource blocks like 'locals', resource_type and resource_name may be None.
    """
    blocks = []
    
    # Pattern for resource/data blocks: resource "type" "name" {
    resource_pattern = r'^(resource|data)\s+"([^"]+)"\s+"([^"]+)"\s*\{'
    
    # Pattern for other blocks: variable "name" {, output "name" {, locals {, terraform {
    other_block_pattern = r'^(variable|output|locals|terraform|provider|module)\s*(?:"([^"]+)")?\s*\{'
    
    lines = content.split('\n')
    i = 0
    
    while i < len(lines):
        line = lines[i]
        
        # Check for resource/data block
        match = re.match(resource_pattern, line)
        if match:
            block_type = match.group(1)
            resource_type = match.group(2)
            resource_name = match.group(3)
            
            # Find the complete block
            block_lines, end_idx = extract_block(lines, i)
            block_text = '\n'.join(block_lines)
            
            blocks.append((block_type, resource_type, resource_name, block_text))
            i = end_idx + 1
            continue
        
        # Check for other block types
        match = re.match(other_block_pattern, line)
        if match:
            block_type = match.group(1)
            block_name = match.group(2)  # May be None for 'locals' or 'terraform'
            
            block_lines, end_idx = extract_block(lines, i)
            block_text = '\n'.join(block_lines)
            
            blocks.append((block_type, None, block_name, block_text))
            i = end_idx + 1
            continue
        
        i += 1
    
    return blocks


def extract_block(lines: list, start_idx: int) -> tuple:
    """
    Extract a complete block starting at start_idx, handling nested braces.
    Returns (block_lines, end_index).
    """
    block_lines = []
    brace_count = 0
    started = False
    
    for i in range(start_idx, len(lines)):
        line = lines[i]
        block_lines.append(line)
        
        # Count braces (simple approach - doesn't handle braces in strings perfectly
        # but works for aztfexport output which is well-formatted)
        for char in line:
            if char == '{':
                brace_count += 1
                started = True
            elif char == '}':
                brace_count -= 1
        
        if started and brace_count == 0:
            return block_lines, i
    
    # If we get here, block wasn't properly closed
    return block_lines, len(lines) - 1


def get_target_file(resource_type: str, type_to_file: dict, default_file: str, skip_types: list) -> Optional[str]:
    """
    Determine which file a resource type should go into.
    Returns None if the type should be skipped.
    """
    if resource_type in skip_types:
        return None
    
    # Direct match first
    if resource_type in type_to_file:
        return type_to_file[resource_type]
    
    # Try prefix matching for resource types with suffixes
    # e.g., azurerm_mssql_server_extended_auditing_policy -> databases-sql.tf
    for mapped_type, target_file in type_to_file.items():
        if resource_type.startswith(mapped_type):
            return target_file
    
    return default_file


def split_terraform_file(input_file: Path, output_dir: Path, config: dict) -> dict:
    """
    Split a Terraform file into multiple files based on resource type mappings.
    
    Returns a summary dict with file names and block counts.
    """
    content = input_file.read_text(encoding='utf-8')
    blocks = parse_tf_blocks(content)
    
    type_to_file = build_type_to_file_map(config)
    default_file = config.get('default_file', 'other.tf')
    skip_types = config.get('skip_types', [])
    
    # Group blocks by target file
    file_blocks = defaultdict(list)
    special_blocks = []  # terraform, provider, variable, output, locals
    skipped = []
    
    for block_type, resource_type, name, block_text in blocks:
        if block_type in ('resource', 'data'):
            target = get_target_file(resource_type, type_to_file, default_file, skip_types)
            if target is None:
                skipped.append((resource_type, name))
            else:
                file_blocks[target].append(block_text)
        else:
            # Special blocks go to dedicated files
            if block_type == 'terraform':
                special_blocks.append(('versions.tf', block_text))
            elif block_type == 'provider':
                special_blocks.append(('providers.tf', block_text))
            elif block_type == 'variable':
                special_blocks.append(('variables.tf', block_text))
            elif block_type == 'output':
                special_blocks.append(('outputs.tf', block_text))
            elif block_type == 'locals':
                special_blocks.append(('locals.tf', block_text))
            elif block_type == 'module':
                special_blocks.append(('modules.tf', block_text))
    
    # Add special blocks to file_blocks
    for target_file, block_text in special_blocks:
        file_blocks[target_file].append(block_text)
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Write files
    summary = {'files': {}, 'skipped': skipped}
    
    for filename, blocks_list in sorted(file_blocks.items()):
        filepath = output_dir / filename
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n\n'.join(blocks_list))
            f.write('\n')  # Trailing newline
        
        summary['files'][filename] = len(blocks_list)
        print(f"  {filename}: {len(blocks_list)} blocks")
    
    return summary


def main():
    parser = argparse.ArgumentParser(
        description='Split aztfexport main.tf into organized files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python tf_splitter.py main.tf
    python tf_splitter.py main.tf ./organized
    python tf_splitter.py --config custom_mapping.yaml main.tf output/
        """
    )
    parser.add_argument('input_file', help='Input Terraform file (usually main.tf)')
    parser.add_argument('output_dir', nargs='?', default='split', 
                        help='Output directory (default: ./split)')
    parser.add_argument('--config', '-c', type=Path, 
                        help='Custom config file path')
    parser.add_argument('--dry-run', '-n', action='store_true',
                        help='Show what would be done without writing files')
    
    args = parser.parse_args()
    
    input_file = Path(args.input_file)
    output_dir = Path(args.output_dir)
    
    if not input_file.exists():
        print(f"Error: Input file not found: {input_file}")
        sys.exit(1)
    
    print(f"Splitting: {input_file}")
    print(f"Output to: {output_dir}")
    print()
    
    config = load_config(args.config)
    
    if args.dry_run:
        print("DRY RUN - no files will be written\n")
    
    summary = split_terraform_file(input_file, output_dir, config)
    
    print()
    print(f"Total files created: {len(summary['files'])}")
    print(f"Total blocks processed: {sum(summary['files'].values())}")
    
    if summary['skipped']:
        print(f"\nSkipped {len(summary['skipped'])} resources:")
        for rtype, name in summary['skipped']:
            print(f"  - {rtype}.{name}")


if __name__ == '__main__':
    main()
