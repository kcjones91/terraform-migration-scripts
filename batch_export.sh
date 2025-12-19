#!/bin/bash
# =============================================================================
# Batch Export Script for Linux/macOS
# =============================================================================
# Exports multiple resource groups from a subscription
#
# Usage: ./batch_export.sh <subscription-id> [--gov]
#
# Edit the RESOURCE_GROUPS array below before running
# =============================================================================

set -euo pipefail

# Configuration
SUBSCRIPTION_ID="${1:-}"
GOV_FLAG="${2:-}"
OUTPUT_BASE="./terraform/subscriptions"

# List your resource groups here (one per line)
RESOURCE_GROUPS=(
    "rg-networking"
    "rg-compute"
    "rg-storage"
    "rg-app1"
)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Functions
print_header() {
    echo -e "${BLUE}============================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}============================================================${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# Validate arguments
if [[ -z "$SUBSCRIPTION_ID" ]]; then
    echo -e "${RED}Usage: $0 <subscription-id> [--gov]${NC}"
    echo ""
    echo "Edit this script to set RESOURCE_GROUPS before running."
    exit 1
fi

print_header "Azure Terraform Batch Export"
echo "Subscription: $SUBSCRIPTION_ID"
echo "Output Base: $OUTPUT_BASE"
if [[ "$GOV_FLAG" == "--gov" ]]; then
    echo "Environment: Azure Government"
fi
echo ""

# Create output directory
mkdir -p "$OUTPUT_BASE"

# Track statistics
TOTAL_RGS=${#RESOURCE_GROUPS[@]}
SUCCESS_COUNT=0
FAILURE_COUNT=0
FAILED_RGS=()

# Export each resource group
for RG in "${RESOURCE_GROUPS[@]}"; do
    echo ""
    print_header "Exporting: $RG ($((SUCCESS_COUNT + FAILURE_COUNT + 1))/$TOTAL_RGS)"

    OUTPUT_DIR="$OUTPUT_BASE/$RG"

    # Build command
    CMD="python3 az_export_rg.py -s $SUBSCRIPTION_ID -g $RG -o $OUTPUT_DIR"
    if [[ "$GOV_FLAG" == "--gov" ]]; then
        CMD="$CMD --gov"
    fi

    # Run export
    if $CMD; then
        print_success "Exported $RG"
        ((SUCCESS_COUNT++))
    else
        print_error "Failed to export $RG"
        ((FAILURE_COUNT++))
        FAILED_RGS+=("$RG")
        echo "Continuing with next resource group..."
    fi

    # Small delay to avoid rate limiting
    if [[ $((SUCCESS_COUNT + FAILURE_COUNT)) -lt $TOTAL_RGS ]]; then
        echo "Waiting 5 seconds..."
        sleep 5
    fi
done

# Print summary
echo ""
print_header "Batch Export Complete!"
echo ""
echo "Total Resource Groups: $TOTAL_RGS"
print_success "Successful: $SUCCESS_COUNT"

if [[ $FAILURE_COUNT -gt 0 ]]; then
    print_error "Failed: $FAILURE_COUNT"
    echo ""
    echo "Failed Resource Groups:"
    for FAILED_RG in "${FAILED_RGS[@]}"; do
        echo "  - $FAILED_RG"
    done
fi

echo ""
echo "Next steps:"
echo "  1. Review each exported directory"
echo "  2. Run 'terraform init' in each directory"
echo "  3. Run 'terraform plan' to verify imports"
echo ""

# Exit with error if any exports failed
if [[ $FAILURE_COUNT -gt 0 ]]; then
    exit 1
fi

exit 0
