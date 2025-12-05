# Strangler Fig Migration - Complete Walkthrough

This document provides step-by-step instructions for migrating legacy Azure infrastructure to Terraform using the Strangler Fig pattern with aztfexport, a catalog layer, and Terragrunt.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Architecture Overview](#2-architecture-overview)
3. [Phase 1: Setup State Storage](#3-phase-1-setup-state-storage)
4. [Phase 2: Import Legacy RGs with aztfexport](#4-phase-2-import-legacy-rgs-with-aztfexport)
5. [Phase 3: Generate Outputs](#5-phase-3-generate-outputs)
6. [Phase 4: Migrate State to Remote Backend](#6-phase-4-migrate-state-to-remote-backend)
7. [Phase 5: Create Subscription Catalog](#7-phase-5-create-subscription-catalog)
8. [Phase 6: Setup Terragrunt for Modern Deployments](#8-phase-6-setup-terragrunt-for-modern-deployments)
9. [Phase 7: Deploy Modern Infrastructure](#9-phase-7-deploy-modern-infrastructure)
10. [Troubleshooting](#10-troubleshooting)
11. [Quick Reference](#11-quick-reference)

---

## 1. Prerequisites

### Required Tools

```powershell
# Azure CLI
az --version  # 2.50+ recommended

# Terraform
terraform --version  # 1.5+ recommended

# aztfexport
aztfexport --version  # Install: go install github.com/Azure/aztfexport@latest

# Terragrunt (for modern deployments)
terragrunt --version  # Install: choco install terragrunt

# Python 3.8+ with PyYAML
python --version
pip install pyyaml --break-system-packages
```

### Required Scripts

Download these scripts to your `scripts/` folder:
- `generate_outputs.py` - Generates outputs from aztfexport main.tf
- `generate_catalog.py` - Creates subscription-level catalog
- `resource_types.yaml` - Resource type configuration (optional)

### Azure Authentication

```powershell
# Login to Azure
az login

# Set subscription
az account set --subscription "YOUR-SUBSCRIPTION-ID"

# Verify
az account show
```

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                              WORKFLOW                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   EXISTING AZURE RGs              aztfexport              TERRAFORM │
│   ┌─────────────────┐            ──────────►         ┌─────────────┐│
│   │ rg-frontend     │                                │ main.tf     ││
│   │ rg-backend      │                                │ providers.tf││
│   │ rg-data         │                                │ (per RG)    ││
│   └─────────────────┘                                └──────┬──────┘│
│                                                             │       │
│                                                             ▼       │
│                                                    generate_outputs.py
│                                                             │       │
│                                                             ▼       │
│                                                      ┌─────────────┐│
│                                                      │ outputs.tf  ││
│                                                      │ locals.tf   ││
│                                                      └──────┬──────┘│
│                                                             │       │
│                                                             ▼       │
│                                                    terraform apply  │
│                                                    (migrate state)  │
│                                                             │       │
│                                                             ▼       │
│   ┌─────────────────────────────────────────────────────────────┐  │
│   │                    STATE STORAGE                             │  │
│   │  legacy/{subscription}/                                      │  │
│   │  ├── rg-frontend.tfstate ──┐                                │  │
│   │  ├── rg-backend.tfstate  ──┼──► catalog.tfstate             │  │
│   │  └── rg-data.tfstate ──────┘         │                      │  │
│   │                                      │                      │  │
│   │  live/{subscription}/                ▼                      │  │
│   │  ├── frontend-vms.tfstate ◄── reads catalog                 │  │
│   │  └── monitoring.tfstate   ◄── reads catalog                 │  │
│   └─────────────────────────────────────────────────────────────┘  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Folder Structure

```
tf-migration/
├── scripts/
│   ├── generate_outputs.py
│   ├── generate_catalog.py
│   └── resource_types.yaml
│
├── legacy-import/
│   └── {subscription-name}/
│       ├── {rg-name-1}/
│       │   ├── main.tf          # aztfexport output
│       │   ├── providers.tf     # Backend + provider config
│       │   ├── locals.tf        # Generated by script
│       │   └── outputs.tf       # Generated by script
│       ├── {rg-name-2}/
│       └── catalog/
│           ├── data.tf          # Reads all RG states
│           ├── outputs.tf       # Aggregated outputs
│           └── providers.tf
│
├── live/                        # Terragrunt deployments
│   ├── terragrunt.hcl
│   └── {subscription-name}/
│       ├── subscription.hcl
│       ├── catalog.hcl
│       └── {deployment-name}/
│           └── terragrunt.hcl
│
└── modules/
    ├── vm/
    └── landing-zone/
```

---

## 3. Phase 1: Setup State Storage

### Create Storage Account

```powershell
# Variables
$RESOURCE_GROUP = "tfstate-rg"
$LOCATION = "eastus"
$STORAGE_ACCOUNT = "tfstatemigrate$(Get-Random -Maximum 9999)"
$CONTAINER = "tfstate"

# Create resource group
az group create --name $RESOURCE_GROUP --location $LOCATION

# Create storage account
az storage account create `
    --name $STORAGE_ACCOUNT `
    --resource-group $RESOURCE_GROUP `
    --location $LOCATION `
    --sku Standard_LRS `
    --encryption-services blob

# Create container
az storage container create `
    --name $CONTAINER `
    --account-name $STORAGE_ACCOUNT

# Output the storage account name (save this!)
Write-Host "Storage Account: $STORAGE_ACCOUNT"
```

### Save Configuration

Create a file to store your backend configuration:

```powershell
# scripts/backend-config.ps1
$env:TF_BACKEND_RG = "tfstate-rg"
$env:TF_BACKEND_STORAGE = "tfstatemigrate3199"  # Your actual name
$env:TF_BACKEND_CONTAINER = "tfstate"
$env:SUBSCRIPTION_ID = "your-subscription-id"
```

---

## 4. Phase 2: Import Legacy RGs with aztfexport

### Step 4.1: Create Folder Structure

```powershell
# Set subscription name (use a short, descriptive name)
$SUBSCRIPTION_NAME = "sub-prod-core"

# Create folders
mkdir -p legacy-import/$SUBSCRIPTION_NAME
cd legacy-import/$SUBSCRIPTION_NAME
```

### Step 4.2: Run aztfexport for Each RG

```powershell
# For each resource group you want to import:
$RG_NAME = "your-resource-group-name"

# Create RG folder and run aztfexport
mkdir $RG_NAME
cd $RG_NAME
aztfexport rg $RG_NAME

# This creates:
#   main.tf       - All resources
#   providers.tf  - Provider configuration
#   terraform.tf  - Local backend (we'll replace this)
#   terraform.tfstate - Local state file
```

### Step 4.3: Verify Import

```powershell
# IMPORTANT: Run plan BEFORE modifying any files
terraform plan

# Expected output: "No changes. Your infrastructure matches the configuration."
# If you see changes, investigate before proceeding!
```

**⚠️ CRITICAL**: Do NOT modify any files until `terraform plan` shows no changes!

---

## 5. Phase 3: Generate Outputs

### Step 5.1: Run generate_outputs.py

```powershell
# Still in the RG folder (e.g., legacy-import/sub-prod-core/rg-frontend/)
python ../../scripts/generate_outputs.py ./main.tf

# This creates:
#   locals.tf   - Maps resources by Azure name
#   outputs.tf  - Exposes resources for catalog consumption
```

### Step 5.2: Verify Generated Files

```powershell
# Check locals.tf
cat locals.tf | head -30

# Check outputs.tf
cat outputs.tf | head -30
```

Example `locals.tf`:
```hcl
locals {
  # Virtual Networks
  all_vnets = {
    "my-vnet" = azurerm_virtual_network.res-0
  }
  
  # Subnets
  all_subnets = {
    "my-vnet/subnet-app" = azurerm_subnet.res-1
    "my-vnet/subnet-data" = azurerm_subnet.res-2
  }
}
```

---

## 6. Phase 4: Migrate State to Remote Backend

### Step 6.1: Delete aztfexport's terraform.tf

```powershell
# CRITICAL: Delete terraform.tf BEFORE adding backend config
Remove-Item terraform.tf

# Verify it's gone
ls *.tf
```

**Why?** aztfexport creates `terraform.tf` with a local backend. We need to replace it with remote backend in `providers.tf`.

### Step 6.2: Update providers.tf with Remote Backend

Edit `providers.tf` to add the backend block:

```hcl
# providers.tf

terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"  # IMPORTANT: Match aztfexport version
    }
  }
  
  backend "azurerm" {
    resource_group_name  = "tfstate-rg"
    storage_account_name = "tfstatemigrate3199"  # Your storage account
    container_name       = "tfstate"
    key                  = "legacy/sub-prod-core/your-rg-name.tfstate"
  }
}

provider "azurerm" {
  features {}
  subscription_id                 = "your-subscription-id"
  use_cli                         = true
  resource_provider_registrations = "none"
}
```

**⚠️ IMPORTANT**: Use `version = "~> 4.0"` to match aztfexport's provider version!

### Step 6.3: Migrate State to Remote

```powershell
# Initialize with migration
terraform init -migrate-state

# When prompted, type "yes" to copy state to remote backend

# Verify state was migrated
terraform state list
```

### Step 6.4: Apply Outputs to Remote State

```powershell
# CRITICAL STEP: You must apply to save outputs to remote state!
terraform apply

# This should show:
#   Changes to Outputs:
#   + vnets = { ... }
#   + subnets = { ... }
#   etc.

# Type "yes" to apply
```

**⚠️ CRITICAL**: Without `terraform apply`, the outputs won't be saved to state and the catalog won't be able to read them!

### Step 6.5: Verify Remote State

```powershell
# Check that outputs are in remote state
terraform output

# Should display all your resource outputs
```

### Repeat for Each RG

Repeat steps 4.2 through 6.5 for each resource group in the subscription.

---

## 7. Phase 5: Create Subscription Catalog

### Step 7.1: Run generate_catalog.py

```powershell
# From the subscription folder (e.g., legacy-import/sub-prod-core/)
cd ..  # Go up from RG folder to subscription folder

python ../scripts/generate_catalog.py .

# This creates:
#   catalog/
#   ├── data.tf        - terraform_remote_state for each RG
#   ├── outputs.tf     - Aggregated outputs
#   ├── providers.tf   - Backend configuration
#   └── README.md      - Documentation
```

### Step 7.2: Initialize and Apply Catalog

```powershell
cd catalog
terraform init
terraform apply
```

### Step 7.3: Verify Catalog Outputs

```powershell
# Check aggregated outputs
terraform output all_vnets
terraform output all_subnets
terraform output all_resource_groups

# Example output:
# all_vnets = {
#   "frontend-vnet" = {
#     "id" = "/subscriptions/.../virtualNetworks/frontend-vnet"
#     "name" = "frontend-vnet"
#     "address_space" = ["10.1.0.0/16"]
#   }
#   "backend-vnet" = { ... }
# }
```

---

## 8. Phase 6: Setup Terragrunt for Modern Deployments

### Step 8.1: Create Root terragrunt.hcl

```powershell
mkdir -p live
cd live
```

Create `live/terragrunt.hcl`:

```hcl
# Root Terragrunt configuration

locals {
  backend_resource_group  = "tfstate-rg"
  backend_storage_account = "tfstatemigrate3199"
  backend_container       = "tfstate"
}

remote_state {
  backend = "azurerm"
  
  generate = {
    path      = "backend.tf"
    if_exists = "overwrite_terragrunt"
  }
  
  config = {
    resource_group_name  = local.backend_resource_group
    storage_account_name = local.backend_storage_account
    container_name       = local.backend_container
    key                  = "${path_relative_to_include()}/terraform.tfstate"
  }
}

generate "provider" {
  path      = "provider.tf"
  if_exists = "overwrite_terragrunt"
  
  contents = <<EOF
terraform {
  required_version = ">= 1.0"
  
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

provider "azurerm" {
  features {}
  use_cli                         = true
  resource_provider_registrations = "none"
}
EOF
}
```

### Step 8.2: Create Subscription Configuration

Create `live/sub-prod-core/subscription.hcl`:

```hcl
locals {
  subscription_id   = "your-subscription-id"
  subscription_name = "sub-prod-core"
  default_location  = "eastus"
  
  legacy_catalog_key = "legacy/sub-prod-core/catalog.tfstate"
  
  subscription_tags = {
    Subscription = "prod-core"
    Environment  = "Production"
  }
}
```

### Step 8.3: Create Catalog Dependency

Create `live/sub-prod-core/catalog.hcl`:

```hcl
dependency "legacy_catalog" {
  config_path = "${get_parent_terragrunt_dir()}/../legacy-import/sub-prod-core/catalog"
  
  mock_outputs = {
    all_vnets = {}
    all_subnets = {}
    all_resource_groups = {}
    all_nsgs = {}
  }
  
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}
```

---

## 9. Phase 7: Deploy Modern Infrastructure

### Option A: Deploy to Existing Legacy RG

Create `live/sub-prod-core/frontend-vms/terragrunt.hcl`:

```hcl
include "root" {
  path = find_in_parent_folders()
}

include "catalog" {
  path   = find_in_parent_folders("catalog.hcl")
  expose = true
}

locals {
  subscription = read_terragrunt_config(find_in_parent_folders("subscription.hcl"))
  target_rg    = "tfmigrate-rg-frontend"  # Existing legacy RG
  subnet_key   = "tfmigrate-frontend-vnet/frontend-subnet-app"
}

terraform {
  source = "${get_parent_terragrunt_dir()}/../modules//vm"
}

inputs = {
  resource_group_name = local.target_rg
  location            = dependency.legacy_catalog.outputs.all_resource_groups[local.target_rg].location
  
  vms = {
    "web-server-01" = {
      size      = "Standard_B2s"
      subnet_id = dependency.legacy_catalog.outputs.all_subnets[local.subnet_key].id
      tags      = { Role = "WebServer" }
    }
  }
  
  common_tags = local.subscription.locals.subscription_tags
}
```

Deploy:

```powershell
cd live/sub-prod-core/frontend-vms
terragrunt apply
```

### Option B: Create New RG with Peering to Legacy

Create `live/sub-prod-core/monitoring-stack/terragrunt.hcl`:

```hcl
include "root" {
  path = find_in_parent_folders()
}

include "catalog" {
  path   = find_in_parent_folders("catalog.hcl")
  expose = true
}

locals {
  subscription    = read_terragrunt_config(find_in_parent_folders("subscription.hcl"))
  legacy_vnet_key = "tfmigrate-frontend-vnet"
}

terraform {
  source = "${get_parent_terragrunt_dir()}/../modules//landing-zone"
}

inputs = {
  create_resource_group = true
  resource_group_name   = "rg-monitoring-prod"
  location              = "eastus"
  
  vnet = {
    name          = "monitoring-vnet"
    address_space = ["10.200.0.0/16"]
    subnets = {
      "monitoring-subnet" = { address_prefix = "10.200.1.0/24" }
    }
  }
  
  vnet_peerings = {
    "to-legacy-frontend" = {
      remote_vnet_id = dependency.legacy_catalog.outputs.all_vnets[local.legacy_vnet_key].id
    }
  }
  
  vms = {
    "prometheus-01" = {
      size   = "Standard_B2s"
      subnet = "monitoring-subnet"
    }
  }
  
  common_tags = local.subscription.locals.subscription_tags
}
```

Deploy:

```powershell
cd live/sub-prod-core/monitoring-stack
terragrunt apply
```

---

## 10. Troubleshooting

### Problem: State Lock Error

```
Error: Error acquiring the state lock
state blob is already locked
```

**Solution:**

```powershell
# Break the lease on the locked blob
az storage blob lease break `
    --blob-name "legacy/sub-prod-core/rg-frontend.tfstate" `
    --container-name "tfstate" `
    --account-name "tfstatemigrate3199"
```

### Problem: Provider Version Mismatch

```
Error: locked provider registry.terraform.io/hashicorp/azurerm 4.33.0 
does not match configured version constraint ~> 3.0
```

**Solution:**

Update `providers.tf` to use version `~> 4.0`:

```hcl
required_providers {
  azurerm = {
    source  = "hashicorp/azurerm"
    version = "~> 4.0"  # Match aztfexport
  }
}
```

### Problem: Catalog Returns Empty Outputs

```hcl
# terraform output shows:
all_vnets = {}
```

**Causes:**
1. Forgot to run `terraform apply` on RG (just did plan)
2. State key path mismatch between RG and catalog

**Solution:**

```powershell
# 1. Apply outputs to each RG
cd legacy-import/sub-prod-core/rg-frontend
terraform apply

# 2. Verify state key in providers.tf matches catalog data.tf
cat providers.tf | grep "key"
# Should match what catalog expects
```

### Problem: Catalog Key Path Has Double Slash

```
State key: legacy//rg-frontend.tfstate  # Wrong!
Should be: legacy/sub-prod-core/rg-frontend.tfstate
```

**Solution:**

This is caused by path resolution bug. Use updated `generate_catalog.py` which:
1. Uses `.resolve()` on paths
2. Extracts key from each RG's `providers.tf`

### Problem: File Lock Error

```
Error: The process cannot access the file because another process has locked it
```

**Solution:**

```powershell
# Close VS Code and other editors
# Kill any hanging terraform processes
Get-Process -Name "terraform" -ErrorAction SilentlyContinue | Stop-Process -Force

# Use a fresh terminal
```

### Problem: Metadata Single Quotes

```hcl
resource_types = ['azurerm_virtual_network', ...]  # Wrong!
```

**Solution:**

Use updated scripts that output double quotes:

```hcl
resource_types = ["azurerm_virtual_network", ...]  # Correct!
```

---

## 11. Quick Reference

### Per-RG Workflow (Repeat for Each RG)

```powershell
# 1. Import
mkdir {rg-name} && cd {rg-name}
aztfexport rg {rg-name}

# 2. Verify (BEFORE any changes)
terraform plan  # Must show "No changes"

# 3. Generate outputs
python ../../scripts/generate_outputs.py ./main.tf

# 4. Delete terraform.tf
Remove-Item terraform.tf

# 5. Edit providers.tf - add backend block with:
#    key = "legacy/{subscription}/{rg-name}.tfstate"
#    version = "~> 4.0"

# 6. Migrate state
terraform init -migrate-state

# 7. Apply outputs (CRITICAL!)
terraform apply
```

### Catalog Workflow

```powershell
# From subscription folder
python ../scripts/generate_catalog.py .
cd catalog
terraform init
terraform apply
terraform output all_vnets  # Verify
```

### Terragrunt Deployment

```powershell
# Single deployment
cd live/{subscription}/{deployment}
terragrunt apply

# All deployments in subscription
cd live/{subscription}
terragrunt run-all apply
```

### State Key Naming Convention

```
legacy/{subscription-name}/{rg-name}.tfstate      # Legacy RG states
legacy/{subscription-name}/catalog.tfstate        # Subscription catalog
live/{subscription-name}/{deployment}/terraform.tfstate  # Modern deployments
```

### Common Catalog References

```hcl
# VNet ID
dependency.legacy_catalog.outputs.all_vnets["vnet-name"].id

# Subnet ID
dependency.legacy_catalog.outputs.all_subnets["vnet-name/subnet-name"].id

# Resource Group location
dependency.legacy_catalog.outputs.all_resource_groups["rg-name"].location

# NSG ID
dependency.legacy_catalog.outputs.all_nsgs["nsg-name"].id

# VM private IP
dependency.legacy_catalog.outputs.all_linux_vms["vm-name"].private_ip_address
```

---

## Summary Checklist

- [ ] Storage account created for state
- [ ] aztfexport run for each RG
- [ ] `terraform plan` shows no changes (before modifications)
- [ ] `generate_outputs.py` run for each RG
- [ ] `terraform.tf` deleted from each RG
- [ ] `providers.tf` updated with remote backend (version ~> 4.0)
- [ ] `terraform init -migrate-state` run for each RG
- [ ] `terraform apply` run for each RG (saves outputs!)
- [ ] `generate_catalog.py` run for subscription
- [ ] Catalog `terraform apply` run
- [ ] Catalog outputs verified
- [ ] Terragrunt root config created
- [ ] Modern deployments working
