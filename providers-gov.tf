# Azure Government Provider Configuration Template
# Copy this to your subscription folder and customize

terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"  # Match aztfexport output version
    }
  }
  required_version = ">= 1.5.0"
}

provider "azurerm" {
  features {
    # Customize feature flags as needed
    key_vault {
      purge_soft_delete_on_destroy    = false
      recover_soft_deleted_key_vaults = true
    }
    
    virtual_machine {
      delete_os_disk_on_deletion     = true
      skip_shutdown_and_force_delete = false
    }
    
    resource_group {
      prevent_deletion_if_contains_resources = false
    }
  }

  # AZURE GOVERNMENT SPECIFIC
  environment = "usgovernment"
  
  # Subscription to manage
  subscription_id = "YOUR_SUBSCRIPTION_ID"
  
  # Optional: Use a specific tenant
  # tenant_id = "YOUR_TENANT_ID"
  
  # Optional: Use service principal auth (for CI/CD)
  # client_id     = "YOUR_CLIENT_ID"
  # client_secret = "YOUR_CLIENT_SECRET"
  # Or use client certificate:
  # client_certificate_path     = "/path/to/cert.pfx"
  # client_certificate_password = "cert-password"
}

# Azure Government endpoints reference:
# - Portal: https://portal.azure.us
# - Resource Manager: https://management.usgovcloudapi.net/
# - Active Directory: https://login.microsoftonline.us
# - Key Vault: https://<vault-name>.vault.usgovcloudapi.net
# - Storage: https://<account>.blob.core.usgovcloudapi.net
