# Azure Terraform Import Toolkit

A set of tools to help migrate large Azure environments to Terraform using aztfexport.

## Overview

This toolkit helps you:
1. **Discover** your Azure subscriptions and resource groups
2. **Create** a standardized folder structure for Terraform
3. **Export** resources using aztfexport
4. **Organize** the generated code into maintainable files
5. **Track** progress across dozens of subscriptions

## Prerequisites

### Required Tools

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.8+ | [python.org](https://www.python.org/) |
| Azure CLI | Latest | [Install](https://docs.microsoft.com/cli/azure/install-azure-cli) |
| aztfexport | Latest | `go install github.com/Azure/aztfexport@latest` or [Releases](https://github.com/Azure/aztfexport/releases) |
| Terraform | 1.5+ | [Install](https://developer.hashicorp.com/terraform/downloads) |

### Python Dependencies

```bash
pip install pyyaml
```

### Azure CLI Login

```bash
# Azure Public
az login

# Azure Government
az cloud set --name AzureUSGovernment
az login
```

## Quick Start

### 1. Discover Your Environment

```bash
# Basic discovery (list subscriptions and RGs)
python az_discover.py

# Include resource counts (slower but more info)
python az_discover.py --include-resources

# Filter to specific subscriptions
python az_discover.py --subscription-filter "prod-*"

# Create folder structure
python az_discover.py --create-structure --base-path ./terraform

# Save inventory for later reference
python az_discover.py --include-resources --output inventory.json
```

### 2. Export a Resource Group

```bash
# Basic export
python az_export_rg.py -s <subscription-id> -g <resource-group-name>

# Azure Government
python az_export_rg.py -s <subscription-id> -g <rg-name> --gov

# Custom output directory
python az_export_rg.py -s <subscription-id> -g <rg-name> -o ./terraform/prod/my-rg
```

### 3. Organize Existing aztfexport Output

If you've already run aztfexport:

```bash
# Split main.tf into organized files
python tf_splitter.py main.tf ./organized

# Use custom mapping config
python tf_splitter.py main.tf ./organized --config my_mapping.yaml
```

## Folder Structure

The toolkit creates this structure:

```
terraform/
├── toolkit/                      # Copy toolkit here
│   ├── tf_splitter.py
│   ├── az_discover.py
│   ├── az_export_rg.py
│   └── config/
│       └── resource_mapping.yaml
├── templates/                    # Provider/backend templates
│   ├── providers-gov.tf
│   ├── providers-public.tf
│   └── backend.tf
├── subscriptions/
│   ├── prod-core/
│   │   ├── backend.tf
│   │   ├── providers.tf
│   │   ├── README.md
│   │   ├── rg-networking/
│   │   │   ├── README.md
│   │   │   ├── networking.tf
│   │   │   ├── networking-nsgs.tf
│   │   │   └── ...
│   │   └── rg-compute/
│   │       ├── compute.tf
│   │       ├── compute-disks.tf
│   │       └── ...
│   ├── prod-app1/
│   └── .../
└── inventory.json                # Full environment inventory
```

## Customizing Resource Organization

Edit `config/resource_mapping.yaml` to control how resources are organized:

```yaml
mappings:
  # Add your custom mappings
  my-custom-file.tf:
    - azurerm_some_resource
    - azurerm_another_resource

  # Modify existing mappings
  compute.tf:
    - azurerm_linux_virtual_machine
    - azurerm_windows_virtual_machine
    # Add more...

# Skip resources you don't want to manage
skip_types:
  - azurerm_resource_group
  - azurerm_role_assignment
```

## Workflow for Large Environments

### Phase 1: Discovery and Planning (Day 1)

```bash
# 1. Run discovery with full resource counts
python az_discover.py --include-resources --output inventory.json

# 2. Review the inventory
cat inventory.json | jq '.subscriptions[] | {name, rg_count: .resource_groups | length}'

# 3. Create folder structure
python az_discover.py --create-structure --base-path ./terraform

# 4. Set up remote state storage (see templates/backend.tf for instructions)
```

### Phase 2: Pilot Export (Day 2-3)

```bash
# 1. Pick a low-risk subscription (dev/test)
# 2. Export one resource group
python az_export_rg.py -s <dev-sub-id> -g <simple-rg> -o ./terraform/subscriptions/dev/simple-rg

# 3. Review and validate
cd ./terraform/subscriptions/dev/simple-rg
terraform init
terraform plan  # Should show no changes

# 4. Iterate on resource_mapping.yaml based on what you learn
```

### Phase 3: Extract Modules (Week 1-2)

As you export more resource groups, identify patterns:

```bash
# Common patterns to modularize:
# - Virtual machines with NICs and disks
# - App Service + Service Plan
# - Storage account with containers
# - Key Vault with access policies
```

### Phase 4: Batch Export (Week 2+)

```bash
# Export remaining subscriptions
# You can parallelize across team members

# Example batch script
for rg in rg-app1 rg-app2 rg-app3; do
  python az_export_rg.py -s $SUB_ID -g $rg -o ./terraform/subscriptions/prod/$rg
done
```

## Azure Government Notes

### Environment Setup

```bash
# Set Azure CLI to Government
az cloud set --name AzureUSGovernment
az login

# Verify
az cloud show --query name
# Should output: "AzureUSGovernment"
```

### Key Differences

| Feature | Public | Government |
|---------|--------|------------|
| Portal | portal.azure.com | portal.azure.us |
| ARM Endpoint | management.azure.com | management.usgovcloudapi.net |
| AD Endpoint | login.microsoftonline.com | login.microsoftonline.us |
| Provider env | (default) | `environment = "usgovernment"` |

### aztfexport with Government

```bash
# aztfexport auto-detects from Azure CLI, but you can force it:
aztfexport resource-group my-rg --env usgovernment

# Or use the wrapper script:
python az_export_rg.py -s <sub-id> -g <rg> --gov
```

## Troubleshooting

### aztfexport hangs or times out

```bash
# Try interactive mode to see what's happening
python az_export_rg.py -s <sub-id> -g <rg> --interactive

# Or run aztfexport directly with verbose logging
aztfexport resource-group my-rg --log-level=DEBUG
```

### terraform plan shows changes after import

Common causes:
1. **Timeouts blocks** - aztfexport includes default timeouts that may differ
2. **Computed fields** - Some fields are computed and will always show changes
3. **Ignore changes** - Add lifecycle blocks for fields managed outside Terraform

```hcl
resource "azurerm_linux_virtual_machine" "example" {
  # ...
  
  lifecycle {
    ignore_changes = [
      tags["LastModified"],
      admin_password,  # If using key-based auth
    ]
  }
}
```

### Missing resources in export

```bash
# Check if resource is supported by aztfexport
aztfexport mapping <resource-type>

# Some resources may need manual import
terraform import azurerm_some_resource.name /subscriptions/.../resource-id
```

### Rate limiting

```bash
# If you hit Azure API rate limits, add delays between RG exports
# Or export during off-peak hours
```

## File Reference

| File | Purpose |
|------|---------|
| `tf_splitter.py` | Splits main.tf into organized files |
| `az_discover.py` | Discovers Azure environment, creates folder structure |
| `az_export_rg.py` | Wrapper around aztfexport with organization |
| `config/resource_mapping.yaml` | Configures how resources are organized |
| `templates/providers-gov.tf` | Azure Government provider template |
| `templates/providers-public.tf` | Azure Public provider template |
| `templates/backend.tf` | Remote state backend template |

## Tips for Success

1. **Start small** - Export a simple RG first, validate, then scale up
2. **Don't over-modularize** - For imported infra, organized files > deep modules
3. **Use remote state early** - Set up backend storage before doing real exports
4. **Track progress** - Use the READMEs with checkboxes to track completion
5. **Review before committing** - aztfexport output needs cleanup before production use
6. **Test with plan** - Always run `terraform plan` after import to verify

## Contributing

Feel free to customize these scripts for your environment. Common customizations:
- Add new resource types to `resource_mapping.yaml`
- Modify folder structure in `az_discover.py`
- Add post-processing steps to `az_export_rg.py`
