$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$server = 'D:\桌面\测试服务器'

$api = Get-ChildItem (Join-Path $server 'libraries\io\papermc\paper\paper-api') `
    -Recurse -Filter 'paper-api-*.jar' -ErrorAction Stop |
    Select-Object -First 1
if (-not $api) {
    throw "paper-api jar not found under $server\libraries"
}

$libraryJars = Get-ChildItem (Join-Path $server 'libraries') `
    -Recurse -Filter '*.jar' -ErrorAction Stop |
    Select-Object -ExpandProperty FullName

$classpath = (@($api.FullName) + $libraryJars) -join ';'
$classes = Join-Path $root 'build\classes'
Remove-Item $classes -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $classes -Force | Out-Null

$sources = Get-ChildItem (Join-Path $root 'src\main\java') -Recurse -Filter '*.java' |
    Select-Object -ExpandProperty FullName

& javac --release 25 -encoding UTF-8 -cp $classpath -d $classes $sources
if ($LASTEXITCODE -ne 0) {
    throw 'javac failed'
}

Copy-Item (Join-Path $root 'src\main\resources\plugin.yml') $classes -Force
Copy-Item (Join-Path $root 'src\main\resources\config.yml') $classes -Force

$jarPath = Join-Path $root 'SuperDebug-1.1.0.jar'
Remove-Item $jarPath -Force -ErrorAction SilentlyContinue
& jar --create --file $jarPath -C $classes .
if ($LASTEXITCODE -ne 0) {
    throw 'jar failed'
}

$plugins = Join-Path $server 'plugins'
Copy-Item $jarPath $plugins -Force
Write-Host "Built: $jarPath"
Write-Host "Installed: $(Join-Path $plugins 'SuperDebug-1.1.0.jar')"
