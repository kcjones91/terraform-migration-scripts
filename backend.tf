# Azure Remote State Backend Configuration
# 
# This template configures Terraform to store state in Azure Blob Storage.
# You need to create the storage account first (see setup instructions below).

# =============================================================================
# BACKEND CONFIGURATION
# =============================================================================

terraform {
  backend "azurerm" {
    # Storage account details
    resource_group_name  = "rg-terraform-state"
    storage_account_name = "stterraformstate"  # Must be globally unique
    container_name       = "tfstate"
    
    # State file key - UNIQUE PER SUBSCRIPTION/ENVIRONMENT
    key = "subscription-name.tfstate"
    
    # For Azure Government, uncomment:
    # environment = "usgovernment"
    
    # Optional: Use a specific subscription for state (if different from managed resources)
    # subscription_id = "state-subscription-id"
  }
}

# =============================================================================
# SETUP INSTRUCTIONS
# =============================================================================
#
# 1. Create a dedicated subscription or resource group for Terraform state
#
# 2. Create the storage account (run these commands once):
#
#    # For Azure Public:
#    az group create --name rg-terraform-state --location eastus
#    az storage account create \
#      --name stterraformstate \
#      --resource-group rg-terraform-state \
#      --location eastus \
#      --sku Standard_LRS \
#      --min-tls-version TLS1_2 \
#      --allow-blob-public-access false
#    az storage container create \
#      --name tfstate \
#      --account-name stterraformstate
#
#    # For Azure Government:
#    az cloud set --name AzureUSGovernment
#    az group create --name rg-terraform-state --location usgovvirginia
#    az storage account create \
#      --name stterraformstategov \
#      --resource-group rg-terraform-state \
#      --location usgovvirginia \
#      --sku Standard_LRS \
#      --min-tls-version TLS1_2 \
#      --allow-blob-public-access false
#    az storage container create \
#      --name tfstate \
#      --account-name stterraformstategov
#
# 3. Enable versioning for state recovery:
#    az storage account blob-service-properties update \
#      --account-name stterraformstate \
#      --enable-versioning true
#
# 4. (Optional) Enable soft delete:
#    az storage account blob-service-properties update \
#      --account-name stterraformstate \
#      --enable-delete-retention true \
#      --delete-retention-days 30
#
# 5. (Optional) Add a resource lock:
#    az lock create \
#      --name "terraform-state-lock" \
#      --resource-group rg-terraform-state \
#      --lock-type CanNotDelete
#
# =============================================================================
# STATE FILE NAMING CONVENTION
# =============================================================================
#
# Recommended: Use a consistent naming pattern for state files:
#
#   {environment}-{subscription-name}.tfstate
#   
# Examples:
#   - prod-core-infrastructure.tfstate
#   - prod-app-frontend.tfstate
#   - dev-shared-services.tfstate
#   - platform-networking.tfstate
#
# =============================================================================
