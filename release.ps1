param(
  [string]$Version = "",
  [string]$BackendUrl = "",
  [switch]$SkipInstall,
  [switch]$Clean
)

$ErrorActionPreference = "Stop"

function Write-Step {
  param([string]$Message)
  Write-Host ""
  Write-Host "==> $Message" -ForegroundColor Cyan
}

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

Write-Step "Preparing release from $repoRoot"

if ($Version) {
  Write-Step "Updating package version to $Version"
  npm version $Version --no-git-tag-version
}

if ($BackendUrl) {
  Write-Step "Using backend URL $BackendUrl"
  $env:BACKEND_URL = $BackendUrl
}

if ($Clean -and (Test-Path ".\dist")) {
  Write-Step "Cleaning dist"
  Remove-Item -LiteralPath ".\dist" -Recurse -Force
}

if (-not $SkipInstall) {
  Write-Step "Installing npm dependencies"
  npm install
}

Write-Step "Building Windows installer"
npm run dist

Write-Step "Release artifacts"
$artifacts = Get-ChildItem ".\dist" -File |
  Where-Object {
    $_.Name -like "*.exe" -or
    $_.Name -like "*.msi" -or
    $_.Name -like "*.blockmap" -or
    $_.Name -eq "latest.yml"
  } |
  Select-Object Name, Length, LastWriteTime

if (-not $artifacts) {
  throw "Build finished, but no release artifacts were found in dist."
}

$artifacts | Format-Table -AutoSize

Write-Host ""
Write-Host "Release complete. Upload the files above from the dist folder." -ForegroundColor Green
