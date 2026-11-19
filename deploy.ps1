# deploy.ps1 - Deploy the website directory to Cloudflare Pages (Direct Upload via wrangler).
# ============================================================
# Credentials are read from environment variables ONLY (never hard-coded):
#   CLOUDFLARE_API_TOKEN       API token / KEY
#   CLOUDFLARE_ACCOUNT_ID      Cloudflare account ID
#   CLOUDFLARE_PAGES_PROJECT   Pages project name (e.g. noppnb666)
#
# Usage (PowerShell):
#   $env:CLOUDFLARE_API_TOKEN='...'
#   $env:CLOUDFLARE_ACCOUNT_ID='...'
#   $env:CLOUDFLARE_PAGES_PROJECT='noppnb666'
#   powershell -ExecutionPolicy Bypass -File deploy.ps1
#
# Or persist them with `setx` once, then run the script directly.
# Deploys only the website directory; it does not touch the program code.
# ============================================================

$ErrorActionPreference = 'Stop'

# ---- 1) Read credentials from environment variables ----
$token   = $env:CLOUDFLARE_API_TOKEN
$account = $env:CLOUDFLARE_ACCOUNT_ID
$project = $env:CLOUDFLARE_PAGES_PROJECT
if (-not $token)   { throw "Missing environment variable CLOUDFLARE_API_TOKEN - set it first (see the script header)." }
if (-not $account) { throw "Missing environment variable CLOUDFLARE_ACCOUNT_ID - set it first." }
if (-not $project) { throw "Missing environment variable CLOUDFLARE_PAGES_PROJECT - set it first." }

# ---- 2) Website directory (repository layout: <repo>/web) ----
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$web  = Join-Path $root 'web'
if (-not (Test-Path $web)) { throw "Website directory not found: $web" }
Write-Host "[deploy] Site: $web"

# ---- 3) Find wrangler / npx ----
$wrangler = Get-Command wrangler -ErrorAction SilentlyContinue
$npx      = Get-Command npx      -ErrorAction SilentlyContinue

$env:CLOUDFLARE_ACCOUNT_ID = $account
$env:CLOUDFLARE_API_TOKEN  = $token

if ($wrangler) {
    Write-Host "[deploy] Using wrangler: $($wrangler.Source)"
    & $wrangler.Source pages deploy $web --project-name=$project --branch=main --commit-dirty=true
} elseif ($npx) {
    Write-Host "[deploy] Using npx wrangler: $($npx.Source)"
    & $npx.Source wrangler pages deploy $web --project-name=$project --branch=main --commit-dirty=true
} else {
    throw "wrangler or npx not found. Install it first: npm i -g wrangler"
}

if ($LASTEXITCODE -ne 0) {
    throw "Deployment failed (exit code $LASTEXITCODE)"
}

Write-Host ""
Write-Host "[deploy] Deployment finished"
Write-Host "[deploy] Preview: https://$project.pages.dev"
