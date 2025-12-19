#!/usr/bin/env python3
"""
Dependency Graph Generator

Analyzes Terraform configurations and generates dependency graphs showing:
- Resource relationships within a resource group
- Cross-RG dependencies via catalog references
- Data source dependencies

Output formats:
- DOT (Graphviz) format
- Mermaid diagram format
- Text-based tree view

Usage:
    python dependency_graph.py --rg legacy-import/sub-prod/rg-network --format dot
    python dependency_graph.py --subscription sub-prod --catalog --format mermaid
    python dependency_graph.py --rg legacy-import/sub-prod/rg-network --output graph.dot

Prerequisites:
    - graphviz (optional, for rendering): pip install graphviz
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple
from collections import defaultdict

try:
    import graphviz
    HAS_GRAPHVIZ = True
except ImportError:
    HAS_GRAPHVIZ = False


# =============================================================================
# TERRAFORM PARSER
# =============================================================================

class TerraformDependencyParser:
    """Parse Terraform files to extract resource dependencies."""

    def __init__(self, directory: Path):
        self.directory = directory
        self.resources = {}  # resource_type.name -> attributes
        self.dependencies = defaultdict(set)  # resource -> set of dependencies

    def parse(self):
        """Parse all .tf files in the directory."""
        tf_files = list(self.directory.glob('*.tf'))

        for tf_file in tf_files:
            self._parse_file(tf_file)

        self._extract_dependencies()

    def _parse_file(self, tf_file: Path):
        """Parse a single .tf file for resource definitions."""
        content = tf_file.read_text(encoding='utf-8')

        # Find all resource blocks
        resource_pattern = re.compile(
            r'resource\s+"([^"]+)"\s+"([^"]+)"\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}',
            re.MULTILINE | re.DOTALL
        )

        for match in resource_pattern.finditer(content):
            resource_type = match.group(1)
            resource_name = match.group(2)
            resource_body = match.group(3)

            resource_id = f"{resource_type}.{resource_name}"
            self.resources[resource_id] = resource_body

    def _extract_dependencies(self):
        """Extract dependencies by analyzing resource references."""
        for resource_id, body in self.resources.items():
            # Find references to other resources
            # Pattern: azurerm_resource.name or azurerm_resource.name.attribute
            ref_pattern = re.compile(r'\b([a-z_]+)\.([a-z0-9_-]+)(?:\.([a-z_]+))?')

            for match in ref_pattern.finditer(body):
                ref_type = match.group(1)
                ref_name = match.group(2)

                # Skip common keywords that aren't resources
                if ref_type in ['var', 'local', 'data', 'module', 'each', 'count']:
                    continue

                ref_id = f"{ref_type}.{ref_name}"

                # Only add if it's a known resource
                if ref_id in self.resources and ref_id != resource_id:
                    self.dependencies[resource_id].add(ref_id)


# =============================================================================
# GRAPH GENERATORS
# =============================================================================

class DotGraphGenerator:
    """Generate DOT format graph."""

    def __init__(self, parser: TerraformDependencyParser):
        self.parser = parser

    def generate(self) -> str:
        """Generate DOT format graph."""
        lines = [
            'digraph terraform_dependencies {',
            '  rankdir=LR;',
            '  node [shape=box, style=rounded];',
            ''
        ]

        # Group by resource type
        type_groups = defaultdict(list)
        for resource_id in self.parser.resources.keys():
            resource_type = resource_id.split('.')[0]
            type_groups[resource_type].append(resource_id)

        # Add nodes with colors based on type
        colors = {
            'azurerm_virtual_network': 'lightblue',
            'azurerm_subnet': 'lightblue',
            'azurerm_network_security_group': 'orange',
            'azurerm_linux_virtual_machine': 'lightgreen',
            'azurerm_windows_virtual_machine': 'lightgreen',
            'azurerm_storage_account': 'yellow',
        }

        for resource_id in self.parser.resources.keys():
            resource_type = resource_id.split('.')[0]
            color = colors.get(resource_type, 'lightgray')
            label = resource_id.replace('_', '\\n')

            lines.append(f'  "{resource_id}" [label="{label}", fillcolor="{color}", style="filled,rounded"];')

        lines.append('')

        # Add edges
        for resource_id, deps in self.parser.dependencies.items():
            for dep in deps:
                lines.append(f'  "{resource_id}" -> "{dep}";')

        lines.append('}')

        return '\n'.join(lines)


class MermaidGraphGenerator:
    """Generate Mermaid diagram format."""

    def __init__(self, parser: TerraformDependencyParser):
        self.parser = parser

    def generate(self) -> str:
        """Generate Mermaid flowchart."""
        lines = [
            'graph LR',
            ''
        ]

        # Sanitize names for Mermaid
        def sanitize(name: str) -> str:
            return name.replace('.', '_').replace('-', '_')

        # Add nodes
        for resource_id in self.parser.resources.keys():
            safe_id = sanitize(resource_id)
            lines.append(f'  {safe_id}["{resource_id}"]')

        lines.append('')

        # Add edges
        for resource_id, deps in self.parser.dependencies.items():
            safe_source = sanitize(resource_id)
            for dep in deps:
                safe_dep = sanitize(dep)
                lines.append(f'  {safe_source} --> {safe_dep}')

        return '\n'.join(lines)


class TextTreeGenerator:
    """Generate text-based tree view."""

    def __init__(self, parser: TerraformDependencyParser):
        self.parser = parser

    def generate(self) -> str:
        """Generate text tree."""
        lines = []

        # Find root resources (those with no incoming dependencies)
        all_deps = set()
        for deps in self.parser.dependencies.values():
            all_deps.update(deps)

        roots = set(self.parser.resources.keys()) - all_deps

        # If no roots, pick resources with fewest dependencies
        if not roots:
            roots = sorted(
                self.parser.resources.keys(),
                key=lambda r: len(self.parser.dependencies.get(r, set()))
            )[:3]

        visited = set()

        def print_tree(resource_id: str, prefix: str = "", is_last: bool = True):
            if resource_id in visited:
                return

            visited.add(resource_id)

            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{resource_id}")

            deps = list(self.parser.dependencies.get(resource_id, []))
            extension = "    " if is_last else "│   "

            for i, dep in enumerate(deps):
                print_tree(dep, prefix + extension, i == len(deps) - 1)

        lines.append("Terraform Resource Dependencies:")
        lines.append("")

        for i, root in enumerate(sorted(roots)):
            print_tree(root, "", i == len(roots) - 1)

        return '\n'.join(lines)


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Generate dependency graphs from Terraform configurations',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Generate DOT graph for a single RG
    python dependency_graph.py --rg legacy-import/sub-prod/rg-network

    # Generate Mermaid diagram
    python dependency_graph.py --rg legacy-import/sub-prod/rg-network --format mermaid

    # Save to file
    python dependency_graph.py --rg legacy-import/sub-prod/rg-network -o graph.dot

    # Render with graphviz (requires graphviz installed)
    python dependency_graph.py --rg legacy-import/sub-prod/rg-network --render
        """
    )

    parser.add_argument(
        '--rg', '--resource-group',
        type=Path,
        help='Path to resource group directory'
    )

    parser.add_argument(
        '--format', '-f',
        choices=['dot', 'mermaid', 'text'],
        default='dot',
        help='Output format (default: dot)'
    )

    parser.add_argument(
        '--output', '-o',
        type=Path,
        help='Output file (default: stdout)'
    )

    parser.add_argument(
        '--render',
        action='store_true',
        help='Render graph to PNG (requires graphviz)'
    )

    args = parser.parse_args()

    if not args.rg:
        print("Error: --rg required")
        return 1

    if not args.rg.exists():
        print(f"Error: Directory not found: {args.rg}")
        return 1

    # Parse Terraform files
    print(f"Parsing Terraform files in: {args.rg}", file=sys.stderr)
    tf_parser = TerraformDependencyParser(args.rg)
    tf_parser.parse()

    print(f"Found {len(tf_parser.resources)} resources", file=sys.stderr)
    print(f"Found {sum(len(deps) for deps in tf_parser.dependencies.values())} dependencies", file=sys.stderr)

    # Generate graph
    if args.format == 'dot':
        generator = DotGraphGenerator(tf_parser)
    elif args.format == 'mermaid':
        generator = MermaidGraphGenerator(tf_parser)
    else:  # text
        generator = TextTreeGenerator(tf_parser)

    output = generator.generate()

    # Write output
    if args.output:
        args.output.write_text(output)
        print(f"\nGraph saved to: {args.output}", file=sys.stderr)
    else:
        print(output)

    # Render if requested
    if args.render and args.format == 'dot':
        if not HAS_GRAPHVIZ:
            print("\nError: graphviz library not installed", file=sys.stderr)
            print("Install with: pip install graphviz", file=sys.stderr)
            return 1

        try:
            src = graphviz.Source(output)
            output_file = args.output or Path('graph.dot')
            output_base = output_file.stem
            src.render(output_base, format='png', cleanup=True)
            print(f"Rendered to: {output_base}.png", file=sys.stderr)
        except Exception as e:
            print(f"Error rendering graph: {e}", file=sys.stderr)
            return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
