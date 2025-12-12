#!/usr/bin/env python3
"""
az_export_rg.py - Export a resource group using aztfexport, then organize the output

This script:
1. Runs aztfexport for a specified resource group
2. Automatically runs tf_splitter to organize the output
3. Handles Azure Government environment setup
4. Creates a backup of raw aztfexport output

Prerequisites:
    - aztfexport installed (go install github.com/Azure/aztfexport@latest)
    - Azure CLI logged in
    - Python 3.8+

Usage:
    python az_export_rg.py --subscription <sub-id> --resource-group <rg-name>
    python az_export_rg.py -s <sub-id> -g <rg-name> --output-dir ./output
    python az_export_rg.py -s <sub-id> -g <rg-name> --gov  # Azure Government

Cross-platform: Works on Windows and Linux
"""

import os
import sys
import argparse
import subprocess
import shutil
from pathlib import Path
from datetime import datetime


def get_script_dir() -> Path:
    """Get the directory where this script is located."""
    return Path(__file__).parent.resolve()


def check_prerequisites() -> dict:
    """Check that required tools are available."""
    checks = {
        'aztfexport': False,
        'az': False,
        'terraform': False,
    }
    
    for tool in checks:
        try:
            result = subprocess.run(
                [tool, '--version'],
                capture_output=True,
                text=True,
                shell=(sys.platform == 'win32')
            )
            checks[tool] = result.returncode == 0
        except FileNotFoundError:
            checks[tool] = False
    
    return checks


def set_azure_environment(is_gov: bool):
    """Set environment variables for Azure Government if needed."""
    if is_gov:
        # aztfexport uses ARM_ENVIRONMENT
        os.environ['ARM_ENVIRONMENT'] = 'usgovernment'
        os.environ['AZURE_ENVIRONMENT'] = 'AzureUSGovernment'
        print("Set environment for Azure Government")


def run_aztfexport(
    subscription_id: str,
    resource_group: str,
    output_dir: Path,
    is_gov: bool = False,
    non_interactive: bool = True,
    append: bool = False,
) -> bool:
    """
    Run aztfexport for a resource group.
    
    Returns True if successful.
    """
    set_azure_environment(is_gov)
    
    # Build command
    cmd = ['aztfexport', 'resource-group', resource_group]
    
    # Add flags
    cmd.extend(['--output-dir', str(output_dir)])
    cmd.extend(['--subscription', subscription_id])
    
    if non_interactive:
        cmd.append('--non-interactive')
    
    if append:
        cmd.append('--append')
    
    # For Government, may need to set env in the provider config
    if is_gov:
        cmd.extend(['--env', 'usgovernment'])
    
    print(f"\nRunning: {' '.join(cmd)}")
    print("-" * 60)
    
    try:
        result = subprocess.run(
            cmd,
            shell=(sys.platform == 'win32'),
            # Don't capture output - let it stream to console
        )
        return result.returncode == 0
    except FileNotFoundError:
        print("Error: aztfexport not found.")
        print("Install with: go install github.com/Azure/aztfexport@latest")
        return False


def backup_raw_output(output_dir: Path) -> Path:
    """Create a backup of the raw aztfexport output."""
    backup_dir = output_dir.parent / f"{output_dir.name}_raw_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    if output_dir.exists():
        shutil.copytree(output_dir, backup_dir)
        print(f"Backed up raw output to: {backup_dir}")
    
    return backup_dir


def run_splitter(input_file: Path, output_dir: Path, config_path: Path = None) -> bool:
    """Run the tf_splitter script."""
    script_dir = get_script_dir()
    splitter_script = script_dir / 'tf_splitter.py'
    
    if not splitter_script.exists():
        print(f"Warning: tf_splitter.py not found at {splitter_script}")
        print("Skipping organization step.")
        return False
    
    cmd = [sys.executable, str(splitter_script), str(input_file), str(output_dir)]
    
    if config_path:
        cmd.extend(['--config', str(config_path)])
    
    print(f"\nOrganizing output with tf_splitter...")
    print("-" * 60)
    
    result = subprocess.run(cmd)
    return result.returncode == 0


def create_post_export_report(output_dir: Path, resource_group: str, subscription_id: str):
    """Create a report of what was exported and next steps."""
    
    # Count files and blocks
    tf_files = list(output_dir.glob('*.tf'))
    
    report = f'''# Export Report: {resource_group}

**Exported:** {datetime.now().isoformat()}  
**Subscription:** `{subscription_id}`  
**Resource Group:** `{resource_group}`

## Generated Files

'''
    
    for tf_file in sorted(tf_files):
        # Count resource blocks in file
        content = tf_file.read_text(encoding='utf-8')
        resource_count = content.count('resource "')
        report += f"- `{tf_file.name}`: {resource_count} resources\n"
    
    report += '''
## Next Steps

1. **Review the generated code:**
   ```bash
   terraform fmt -recursive
   terraform validate
   ```

2. **Check for issues:**
   - Look for hardcoded values that should be variables
   - Check for sensitive data in outputs
   - Review resource dependencies

3. **Test the import:**
   ```bash
   terraform init
   terraform plan
   ```
   
   The plan should show **no changes** if import was successful.

4. **Common issues to fix:**
   - Remove `timeouts` blocks if they cause drift
   - Fix `ignore_changes` for auto-generated fields
   - Add `lifecycle` blocks for resources managed outside Terraform

## Files to Review

- `other.tf` - Contains resources not in the mapping config
- `compute-extensions.tf` - VM extensions often have drift
- `identity.tf` - Role assignments may reference users/groups

'''
    
    report_path = output_dir / 'EXPORT_REPORT.md'
    report_path.write_text(report)
    print(f"\nExport report created: {report_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Export and organize an Azure resource group with aztfexport',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Basic export
    python az_export_rg.py -s 12345-... -g my-resource-group

    # Azure Government
    python az_export_rg.py -s 12345-... -g my-rg --gov

    # Custom output directory
    python az_export_rg.py -s 12345-... -g my-rg -o ./terraform/my-rg

    # Skip organization (raw aztfexport output only)
    python az_export_rg.py -s 12345-... -g my-rg --skip-organize
        """
    )
    
    parser.add_argument('--subscription', '-s', required=True,
                        help='Azure subscription ID')
    parser.add_argument('--resource-group', '-g', required=True,
                        help='Resource group name to export')
    parser.add_argument('--output-dir', '-o', type=Path, default=None,
                        help='Output directory (default: ./export-<rg-name>)')
    parser.add_argument('--gov', '--government', action='store_true',
                        help='Use Azure Government cloud')
    parser.add_argument('--skip-organize', action='store_true',
                        help='Skip running tf_splitter after export')
    parser.add_argument('--no-backup', action='store_true',
                        help='Skip backing up raw aztfexport output')
    parser.add_argument('--config', '-c', type=Path,
                        help='Custom resource mapping config for tf_splitter')
    parser.add_argument('--interactive', '-i', action='store_true',
                        help='Run aztfexport in interactive mode')
    
    args = parser.parse_args()
    
    # Check prerequisites
    print("Checking prerequisites...")
    checks = check_prerequisites()
    
    missing = [tool for tool, ok in checks.items() if not ok]
    if 'aztfexport' in missing:
        print("\nError: aztfexport not found.")
        print("Install with: go install github.com/Azure/aztfexport@latest")
        print("Or download from: https://github.com/Azure/aztfexport/releases")
        sys.exit(1)
    
    if missing:
        print(f"Warning: Missing tools: {', '.join(missing)}")
    
    # Set output directory
    if args.output_dir is None:
        args.output_dir = Path(f"./export-{args.resource_group}")
    
    args.output_dir = args.output_dir.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\nExporting resource group: {args.resource_group}")
    print(f"Subscription: {args.subscription}")
    print(f"Output directory: {args.output_dir}")
    print(f"Cloud: {'Azure Government' if args.gov else 'Azure Public'}")
    
    # Run aztfexport
    success = run_aztfexport(
        subscription_id=args.subscription,
        resource_group=args.resource_group,
        output_dir=args.output_dir,
        is_gov=args.gov,
        non_interactive=not args.interactive,
    )
    
    if not success:
        print("\nError: aztfexport failed")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("aztfexport completed successfully")
    print("=" * 60)
    
    # Backup raw output before organizing
    main_tf = args.output_dir / 'main.tf'
    
    if not main_tf.exists():
        print(f"\nWarning: main.tf not found in {args.output_dir}")
        print("aztfexport may have created files with different names")
        sys.exit(0)
    
    if not args.no_backup:
        backup_raw_output(args.output_dir)
    
    # Run splitter to organize
    if not args.skip_organize:
        organized_dir = args.output_dir / 'organized'
        run_splitter(main_tf, organized_dir, args.config)
        
        # Move organized files back to main dir (optional)
        print(f"\nOrganized files are in: {organized_dir}")
        print("You can move them to the main directory if desired.")
    
    # Create report
    create_post_export_report(args.output_dir, args.resource_group, args.subscription)
    
    print("\n" + "=" * 60)
    print("Export complete!")
    print("=" * 60)
    print(f"\nNext steps:")
    print(f"  cd {args.output_dir}")
    print(f"  terraform init")
    print(f"  terraform plan")


if __name__ == '__main__':
    main()
