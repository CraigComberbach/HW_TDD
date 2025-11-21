param(
    [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"

# Go to repo root (one level up from scripts/)
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot  = Split-Path -Parent $scriptDir
Set-Location $repoRoot

Write-Host "Repo root: $repoRoot"

# Ensure .venv exists
$venvPath = Join-Path $repoRoot ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "Creating virtualenv at $venvPath..."
    & $PythonExe -m venv $venvPath
} else {
    Write-Host "Using existing virtualenv at $venvPath"
}

# Upgrade pip and install requirements
Write-Host "Installing Python dependencies..."
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r (Join-Path $repoRoot "requirements.txt")

# Find ngspice_con
$ngspiceCmd = Get-Command "ngspice_con" -ErrorAction SilentlyContinue
if ($null -eq $ngspiceCmd) {
    Write-Warning "ngspice_con not found on PATH. Tests that call ngspice will fail."
} else {
    Write-Host "Using ngspice_con at: $($ngspiceCmd.Source)"
}

# Ensure reports directory exists
$reportsDir = Join-Path $repoRoot "reports"
if (-not (Test-Path $reportsDir)) {
    New-Item -ItemType Directory -Path $reportsDir | Out-Null
}

# Run pytest
Write-Host "Running pytest..."
$pytestArgs = @(
    "-m", "pytest",
    "--junitxml", (Join-Path $reportsDir "junit.xml")
)

& $venvPython @pytestArgs

Write-Host "Done. JUnit report written to $($reportsDir)\junit.xml"
