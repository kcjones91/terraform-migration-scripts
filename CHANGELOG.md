# Changelog - Terraform Migration Scripts

## [Unreleased] - 2025-12-19

### Added

#### Centralized Configuration Management
- **[config.yaml](config.yaml)** - Central configuration file for all migration settings
  - Terraform and provider version management
  - Azure backend configuration
  - Artifactory settings
  - Discovery, validation, and workflow settings
- **[config_loader.py](config_loader.py)** - Python module to load and validate configuration
  - Convenience functions for accessing backend config, provider versions
  - Configuration validation
  - Environment-aware settings (Azure Government support)

#### Artifactory Support
- **[providers-artifactory.tf](providers-artifactory.tf)** - Artifactory provider configuration template
  - Multiple authentication methods
  - Backend configuration examples
- **[artifactory_helper.py](artifactory_helper.py)** - Helper script for Artifactory operations
  - Discover existing Artifactory resources
  - Generate Terraform configuration from existing repositories
  - Validate connectivity
  - Export inventory to JSON

#### Cross-Platform Support
- **[batch_export.sh](batch_export.sh)** - Bash equivalent of batch_export.bat for Linux/macOS
  - Colored output
  - Progress tracking
  - Error handling and summary statistics
  - Rate limiting between exports

#### Development Tools
- **[.gitignore](.gitignore)** - Comprehensive gitignore file
  - Terraform state files and directories
  - Python artifacts
  - IDE configurations
  - Sensitive data patterns
  - OS-specific files
  - Migration-specific temporary files

#### Validation and Helper Scripts
- **[validate_migration.py](validate_migration.py)** - Migration validation tool
  - Validates RG state integrity
  - Checks for drift
  - Verifies outputs are present
  - Validates catalog structure
  - Provider version consistency checks
  - Colored console output
- **[dependency_graph.py](dependency_graph.py)** - Dependency graph generator
  - Analyzes Terraform resource dependencies
  - Multiple output formats (DOT, Mermaid, Text)
  - Optional rendering to PNG
  - Helps visualize resource relationships

### Fixed

#### az_discover.py Completion
- Fixed undefined `get_script_dir()` function
- Implemented toolkit file copying functionality
- Added proper file validation
- Enhanced error reporting
- **Interactive path selection** - Choose destination path interactively or via command line
- **Directory validation** - Warns if target directory is not empty
- **Absolute path resolution** - Shows full path for clarity

#### Provider Version Standardization
- Updated [providers-gov.tf](providers-gov.tf) from `~> 3.0` to `~> 4.0`
- Removed deprecated `graceful_shutdown` attribute
- Updated [generate_catalog.py](generate_catalog.py) to use centralized config
- All scripts now reference version 4.0 consistently

### Changed

#### generate_catalog.py Enhancements
- Integrated with config_loader for backend configuration
- Dynamic provider version from central config
- Uses `get_default_backend_config()` for backend settings
- Uses `get_default_output_keys()` for catalog outputs
- Improved version consistency

### Documentation

#### Configuration Files
- All provider templates now include detailed comments
- Authentication setup instructions in provider files
- CI/CD pipeline examples for GitHub Actions and Azure DevOps

## Migration Notes

### For Existing Users

1. **Update Provider Versions**
   ```bash
   # Check your current version
   grep "version" providers.tf

   # Update to 4.0
   sed -i 's/~> 3.0/~> 4.0/' providers.tf
   ```

2. **Adopt Central Configuration (Optional but Recommended)**
   ```bash
   # Copy config template
   cp config.yaml config.local.yaml

   # Edit with your settings
   vi config.local.yaml

   # Set environment variable
   export TF_MIGRATION_CONFIG=config.local.yaml
   ```

3. **Validate Your Migration**
   ```bash
   # Validate configuration
   python config_loader.py

   # Validate specific subscription
   python validate_migration.py --subscription sub-prod-core

   # Check for drift
   python validate_migration.py --subscription sub-prod-core --check-drift
   ```

### Breaking Changes

None. All changes are backward compatible. Scripts fall back to embedded defaults if config.yaml is not present.

### Deprecations

- Using hardcoded backend configuration in scripts is discouraged
- Consider migrating to config.yaml for centralized management

## Installation

### New Dependencies

For full functionality, install optional Python packages:

```bash
# Core functionality
pip install pyyaml

# Artifactory support
pip install requests

# Dependency graph rendering
pip install graphviz

# All at once
pip install pyyaml requests graphviz
```

### Bash Scripts (Linux/macOS)

Make shell scripts executable:

```bash
chmod +x batch_export.sh
chmod +x *.py
```

## Usage Examples

### Discover Artifactory Resources

```bash
export ARTIFACTORY_ACCESS_TOKEN="your-token"
python artifactory_helper.py discover --url https://artifactory.example.com -o inventory.json
```

### Generate Terraform for Artifactory

```bash
python artifactory_helper.py generate --url https://artifactory.example.com -o repos.tf
```

### Validate Migration

```bash
# Validate single subscription
python validate_migration.py --subscription sub-prod-core

# Validate catalog only
python validate_migration.py --subscription sub-prod-core --catalog-only

# Check for drift
python validate_migration.py --subscription sub-prod-core --check-drift
```

### Generate Dependency Graph

```bash
# DOT format
python dependency_graph.py --rg legacy-import/sub-prod/rg-network -o graph.dot

# Mermaid format
python dependency_graph.py --rg legacy-import/sub-prod/rg-network --format mermaid

# Render to PNG
python dependency_graph.py --rg legacy-import/sub-prod/rg-network --render
```

### Batch Export (Linux/macOS)

```bash
# Edit RESOURCE_GROUPS array in batch_export.sh first
./batch_export.sh subscription-id

# Azure Government
./batch_export.sh subscription-id --gov
```

## Testing

To test the configuration system:

```bash
# Validate configuration
python config_loader.py

# Test Artifactory connectivity
python artifactory_helper.py validate

# Run full migration validation
python validate_migration.py --subscription your-sub-name
```

## Contributors

- Automated improvements based on code review findings
- Enhanced cross-platform compatibility
- Added enterprise tooling support (Artifactory)

## See Also

- [README.md](readme.md) - Main documentation
- [config.yaml](config.yaml) - Configuration reference
- [resource_mapping.yaml](resource_mapping.yaml) - Resource type mappings
