@echo off
REM Batch Export Script for Windows
REM Exports multiple resource groups from a subscription
REM 
REM Usage: batch_export.bat <subscription-id> [--gov]
REM
REM Edit the RESOURCE_GROUPS list below before running

setlocal enabledelayedexpansion

REM Configuration
set SUBSCRIPTION_ID=%1
set GOV_FLAG=%2
set OUTPUT_BASE=.\terraform\subscriptions

REM List your resource groups here (one per line)
set RESOURCE_GROUPS=rg-networking rg-compute rg-storage rg-app1

REM Validate arguments
if "%SUBSCRIPTION_ID%"=="" (
    echo Usage: batch_export.bat ^<subscription-id^> [--gov]
    echo.
    echo Edit this script to set RESOURCE_GROUPS before running.
    exit /b 1
)

echo ============================================================
echo Azure Terraform Batch Export
echo ============================================================
echo Subscription: %SUBSCRIPTION_ID%
echo Output Base: %OUTPUT_BASE%
if "%GOV_FLAG%"=="--gov" echo Environment: Azure Government
echo.

REM Create output directory
if not exist "%OUTPUT_BASE%" mkdir "%OUTPUT_BASE%"

REM Export each resource group
for %%G in (%RESOURCE_GROUPS%) do (
    echo.
    echo ============================================================
    echo Exporting: %%G
    echo ============================================================
    
    set OUTPUT_DIR=%OUTPUT_BASE%\%%G
    
    if "%GOV_FLAG%"=="--gov" (
        python az_export_rg.py -s %SUBSCRIPTION_ID% -g %%G -o !OUTPUT_DIR! --gov
    ) else (
        python az_export_rg.py -s %SUBSCRIPTION_ID% -g %%G -o !OUTPUT_DIR!
    )
    
    if !errorlevel! neq 0 (
        echo ERROR: Failed to export %%G
        echo Continuing with next resource group...
    ) else (
        echo SUCCESS: Exported %%G
    )
    
    REM Small delay to avoid rate limiting
    timeout /t 5 /nobreak >nul
)

echo.
echo ============================================================
echo Batch export complete!
echo ============================================================
echo.
echo Next steps:
echo   1. Review each exported directory
echo   2. Run 'terraform init' in each directory
echo   3. Run 'terraform plan' to verify imports

endlocal
