# deploy.ps1 — 部署站点到 Cloudflare Pages（Direct Upload via wrangler）
# ============================================================
# 凭据全部从环境变量读取（绝不硬编码）：
#   CLOUDFLARE_API_TOKEN       API 令牌 / KEY
#   CLOUDFLARE_ACCOUNT_ID      Cloudflare 账户 ID
#   CLOUDFLARE_PAGES_PROJECT   Pages 项目名（如 noppnb666）
#
# 用法（PowerShell）：
#   $env:CLOUDFLARE_API_TOKEN='...'
#   $env:CLOUDFLARE_ACCOUNT_ID='...'
#   $env:CLOUDFLARE_PAGES_PROJECT='noppnb666'
#   powershell -ExecutionPolicy Bypass -File deploy.ps1
#
# 或先 setx 永久写入用户环境变量，之后直接运行。
# 只部署站点目录，不改动程序代码。
# ============================================================

$ErrorActionPreference = 'Stop'

# ---- 1) 从环境变量读取凭据 ----
$token   = $env:CLOUDFLARE_API_TOKEN
$account = $env:CLOUDFLARE_ACCOUNT_ID
$project = $env:CLOUDFLARE_PAGES_PROJECT
if (-not $token)   { throw "缺少环境变量 CLOUDFLARE_API_TOKEN —— 请先设置（见脚本注释）。" }
if (-not $account) { throw "缺少环境变量 CLOUDFLARE_ACCOUNT_ID —— 请先设置。" }
if (-not $project) { throw "缺少环境变量 CLOUDFLARE_PAGES_PROJECT —— 请先设置。" }

# ---- 2) 站点目录 ----
$web = 'D:\桌面\版本更新检查'
if (-not (Test-Path $web)) { throw "站点目录不存在: $web" }
Write-Host "[deploy] 站点: $web"

# ---- 3) 找到 wrangler / npx ----
$wrangler = Get-Command wrangler -ErrorAction SilentlyContinue
$npx      = Get-Command npx      -ErrorAction SilentlyContinue

$env:CLOUDFLARE_ACCOUNT_ID = $account
$env:CLOUDFLARE_API_TOKEN  = $token

if ($wrangler) {
    Write-Host "[deploy] 使用 wrangler: $($wrangler.Source)"
    & $wrangler.Source pages deploy $web --project-name=$project --branch=main --commit-dirty=true
} elseif ($npx) {
    Write-Host "[deploy] 使用 npx wrangler: $($npx.Source)"
    & $npx.Source wrangler pages deploy $web --project-name=$project --branch=main --commit-dirty=true
} else {
    throw "未找到 wrangler 或 npx，请先安装：npm i -g wrangler"
}

if ($LASTEXITCODE -ne 0) {
    throw "部署失败（退出码 $LASTEXITCODE）"
}

Write-Host ""
Write-Host "[deploy] 部署完成 ✔"
Write-Host "[deploy] 预览: https://$project.pages.dev"
