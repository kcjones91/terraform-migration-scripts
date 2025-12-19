# =============================================================================
# Artifactory Provider Configuration Template
# =============================================================================
# This template configures Terraform to manage JFrog Artifactory resources.
# Use this alongside Azure resources for comprehensive infrastructure management.

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    artifactory = {
      source  = "jfrog/artifactory"
      version = "~> 10.0"
    }
  }

  # Optional: Store Artifactory state in Artifactory itself
  backend "artifactory" {
    url      = "https://artifactory.example.com"
    repo     = "terraform-state-generic"
    subpath  = "artifactory"
    # Authentication via environment variables:
    # ARTIFACTORY_ACCESS_TOKEN or
    # ARTIFACTORY_USERNAME + ARTIFACTORY_PASSWORD
  }

  # Alternative: Store Artifactory state in Azure (recommended for mixed environments)
  # backend "azurerm" {
  #   resource_group_name  = "tfstate-rg"
  #   storage_account_name = "tfstatemigrate3199"
  #   container_name       = "tfstate"
  #   key                  = "artifactory/main.tfstate"
  # }
}

provider "artifactory" {
  # Artifactory instance URL
  url = "https://artifactory.example.com"

  # Authentication Methods (choose one):

  # Method 1: Access Token (Recommended)
  # Set environment variable: ARTIFACTORY_ACCESS_TOKEN
  # access_token = var.artifactory_access_token

  # Method 2: API Key
  # Set environment variable: ARTIFACTORY_API_KEY
  # api_key = var.artifactory_api_key

  # Method 3: Username/Password
  # Set environment variables: ARTIFACTORY_USERNAME and ARTIFACTORY_PASSWORD
  # username = var.artifactory_username
  # password = var.artifactory_password
}

# =============================================================================
# Example Variables
# =============================================================================

variable "artifactory_url" {
  description = "Artifactory instance URL"
  type        = string
  default     = "https://artifactory.example.com"
}

# Don't hardcode credentials! Use environment variables or secure vaults
# variable "artifactory_access_token" {
#   description = "Artifactory access token"
#   type        = string
#   sensitive   = true
# }

# =============================================================================
# Authentication Setup Instructions
# =============================================================================
#
# For local development:
#   export ARTIFACTORY_ACCESS_TOKEN="your-token-here"
#   export ARTIFACTORY_URL="https://artifactory.example.com"
#
# For CI/CD pipelines (Azure DevOps):
#   - Store credentials in Azure Key Vault
#   - Reference in pipeline variables
#   - Set as environment variables before terraform commands
#
# For CI/CD pipelines (GitHub Actions):
#   - Store as GitHub Secrets
#   - Reference in workflow:
#       env:
#         ARTIFACTORY_ACCESS_TOKEN: ${{ secrets.ARTIFACTORY_ACCESS_TOKEN }}
#
# =============================================================================
