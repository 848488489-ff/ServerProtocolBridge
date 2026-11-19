# Deploys the website directory to Cloudflare Pages via wrangler.
#
# Credentials are read from cloudflare_credentials.json in the repo root
# (NOT committed; see .gitignore) or from environment variables:
#   CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN, CLOUDFLARE_PAGES_PROJECT
#
# Usage: powershell -ExecutionPolicy Bypass -File tools\deploy_website.ps1
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$web = Join-Path $root 'web'   # website source directory
if (-not (Test-Path $web)) {
    $web = Join-Path $root 'web'
}

# Load credentials.
$credFile = Join-Path $root 'cloudflare_credentials.json'
$accountId = $env:CLOUDFLARE_ACCOUNT_ID
$apiToken = $env:CLOUDFLARE_API_TOKEN
$project = $env:CLOUDFLARE_PAGES_PROJECT
if (Test-Path $credFile) {
    $cred = Get-Content $credFile -Raw | ConvertFrom-Json
    if (-not $accountId) { $accountId = $cred.account_id }
    if (-not $apiToken) { $apiToken = $cred.api_token }
    if (-not $project) { $project = $cred.project_name }
}
if (-not $accountId -or -not $apiToken -or -not $project) {
    throw "Missing Cloudflare credentials. Fill cloudflare_credentials.json (account_id, api_token, project_name) or set CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN / CLOUDFLARE_PAGES_PROJECT."
}

$env:CLOUDFLARE_ACCOUNT_ID = $accountId
$env:CLOUDFLARE_API_TOKEN = $apiToken

# Prefer a local wrangler if installed, otherwise npx.
$wrangler = Get-Command wrangler -ErrorAction SilentlyContinue
$npx = Get-Command npx -ErrorAction SilentlyContinue
if ($wrangler) {
    & $wrangler.Source pages deploy $web --project-name=$project --branch=main --commit-dirty=true
} elseif ($npx) {
    & $npx.Source wrangler pages deploy $web --project-name=$project --branch=main --commit-dirty=true
} else {
    throw "Neither wrangler nor npx is available. Install via: npm i -g wrangler"
}

if ($LASTEXITCODE -ne 0) {
    throw "wrangler pages deploy failed (exit $LASTEXITCODE)"
}
Write-Host "Deployed $web to Cloudflare Pages project '$project'."
