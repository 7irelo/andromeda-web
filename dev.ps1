# =============================================================================
# Andromeda – Local Development Launcher (PowerShell)
# Starts infrastructure via Docker, then runs the Django backend, Celery
# worker + beat, and Angular dev server in separate terminal windows.
#
# Usage:  .\dev.ps1 [-NoClient] [-NoCelery] [-ResetDb]
#
# Requirements: Docker Desktop, Python 3.11+, Node 18+
# =============================================================================
param(
    [switch]$NoClient,
    [switch]$NoCelery,
    [switch]$ResetDb,
    [switch]$Help
)

if ($Help) {
    Write-Host "Usage: .\dev.ps1 [-NoClient] [-NoCelery] [-ResetDb]"
    exit 0
}

$ErrorActionPreference = "Stop"

$Root      = $PSScriptRoot
$ServerDir = Join-Path $Root "server"
$ClientDir = Join-Path $Root "client"

# ── Colours ───────────────────────────────────────────────────────────────────
function Log  ($msg) { Write-Host "[andromeda] $msg" -ForegroundColor Cyan }
function Ok   ($msg) { Write-Host "[andromeda] $msg" -ForegroundColor Green }
function Warn ($msg) { Write-Host "[andromeda] $msg" -ForegroundColor Yellow }
function Die  ($msg) { Write-Host "[andromeda] ERROR: $msg" -ForegroundColor Red; exit 1 }

# ── Track processes for cleanup ───────────────────────────────────────────────
$Jobs = @()

function Stop-All {
    Warn "Stopping background processes..."
    foreach ($job in $Jobs) {
        if ($job -and -not $job.HasExited) {
            $job.Kill() 2>$null
        }
    }
    Log "Stopping Docker infrastructure..."
    docker compose -f "$Root\docker-compose.yml" stop postgres redis rabbitmq neo4j 2>$null
    Ok "Done. Goodbye!"
}

# Register Ctrl+C handler
[Console]::TreatControlCAsInput = $false
$null = Register-ObjectEvent ([System.Console]) CancelKeyPress -Action {
    Stop-All
    exit 0
}

# ── 1. Prerequisite checks ────────────────────────────────────────────────────
Log "Checking prerequisites..."

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Die "Docker is not installed." }
docker info 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { Die "Docker daemon is not running. Start Docker Desktop." }

$Python = $null
foreach ($cmd in @("python", "python3")) {
    if (Get-Command $cmd -ErrorAction SilentlyContinue) { $Python = $cmd; break }
}
if (-not $Python) { Die "Python 3 is not installed." }

if (-not $NoClient) {
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) { Die "Node.js is not installed." }
    if (-not (Get-Command npm  -ErrorAction SilentlyContinue)) { Die "npm is not installed." }
}

Ok "Prerequisites OK."

# ── 2. .env setup ────────────────────────────────────────────────────────────
$EnvFile = Join-Path $Root ".env"
if (-not (Test-Path $EnvFile)) {
    Warn ".env not found – copying from .env.example"
    Copy-Item (Join-Path $Root ".env.example") $EnvFile
    Warn "Review $EnvFile and set required secrets, then re-run."
}

# Local-dev environment variables
$Env:DEBUG                 = "True"
$Env:POSTGRES_HOST         = "localhost"
$Env:POSTGRES_DB           = if ($Env:POSTGRES_DB)       { $Env:POSTGRES_DB }       else { "andromeda" }
$Env:POSTGRES_USER         = if ($Env:POSTGRES_USER)     { $Env:POSTGRES_USER }     else { "andromeda" }
$Env:POSTGRES_PASSWORD     = if ($Env:POSTGRES_PASSWORD) { $Env:POSTGRES_PASSWORD } else { "andromeda_secret" }
$Neo4jPwd                  = if ($Env:NEO4J_PASSWORD)    { $Env:NEO4J_PASSWORD }    else { "andromeda_secret" }
$RedisPwd                  = if ($Env:REDIS_PASSWORD)    { $Env:REDIS_PASSWORD }    else { "redis_secret" }
$RabbitUser                = if ($Env:RABBITMQ_USER)     { $Env:RABBITMQ_USER }     else { "andromeda" }
$RabbitPwd                 = if ($Env:RABBITMQ_PASSWORD) { $Env:RABBITMQ_PASSWORD } else { "andromeda_secret" }
$Env:NEO4J_BOLT_URL        = "bolt://neo4j:$Neo4jPwd@localhost:7687"
$Env:REDIS_URL             = "redis://:$RedisPwd@localhost:6379/0"
$Env:RABBITMQ_URL          = "amqp://${RabbitUser}:${RabbitPwd}@localhost:5672/andromeda"
$Env:SECRET_KEY            = if ($Env:SECRET_KEY) { $Env:SECRET_KEY } else { "django-insecure-local-dev-only" }
$Env:ALLOWED_HOSTS         = "localhost,127.0.0.1"
$Env:CORS_ALLOWED_ORIGINS  = "http://localhost:4200,http://127.0.0.1:4200"

# ── 3. Start infrastructure ───────────────────────────────────────────────────
Log "Starting infrastructure (postgres, redis, rabbitmq, neo4j)..."
docker compose -f "$Root\docker-compose.yml" up -d postgres redis rabbitmq neo4j
if ($LASTEXITCODE -ne 0) { Die "docker compose failed." }

# ── 4. Wait for healthy services ──────────────────────────────────────────────
function Wait-Healthy($service, $timeoutSec = 90) {
    Log "Waiting for $service to be healthy..."
    $elapsed = 0
    do {
        Start-Sleep -Seconds 3
        $elapsed += 3
        $status = docker compose -f "$Root\docker-compose.yml" ps $service 2>&1
        if ($status -match "healthy") { Ok "$service is healthy."; return }
        Write-Host -NoNewline "."
        if ($elapsed -ge $timeoutSec) { Die "$service did not become healthy within ${timeoutSec}s." }
    } while ($true)
}

Wait-Healthy "postgres"  90
Wait-Healthy "redis"     60
Wait-Healthy "rabbitmq"  90
Wait-Healthy "neo4j"     200

# ── 5. Python virtual environment ─────────────────────────────────────────────
$VenvDir = $null
foreach ($candidate in @("Tempandromeda_venv", ".venv", "venv")) {
    $path = Join-Path $Root $candidate
    if (Test-Path $path) { $VenvDir = $path; break }
}
if (-not $VenvDir) {
    $VenvDir = Join-Path $Root ".venv"
    Log "Creating virtual environment at $VenvDir ..."
    & $Python -m venv $VenvDir
}

$Activate = Join-Path $VenvDir "Scripts\Activate.ps1"
if (-not (Test-Path $Activate)) { Die "Could not find $Activate" }
. $Activate
Ok "Virtual environment activated."

# ── 6. Install Python dependencies ───────────────────────────────────────────
Log "Installing Python dependencies..."
pip install -q --upgrade pip
pip install -q -r (Join-Path $ServerDir "requirements.txt")
Ok "Python dependencies installed."

# ── 7. Node dependencies ──────────────────────────────────────────────────────
if (-not $NoClient -and -not (Test-Path (Join-Path $ClientDir "node_modules"))) {
    Log "Installing Node dependencies..."
    npm --prefix $ClientDir ci
    Ok "Node dependencies installed."
}

# ── 8. Reset DB if requested ──────────────────────────────────────────────────
if ($ResetDb) {
    Warn "--ResetDb: dropping and re-creating the database..."
    docker compose -f "$Root\docker-compose.yml" exec -T postgres `
        psql -U $Env:POSTGRES_USER -c "DROP DATABASE IF EXISTS $Env:POSTGRES_DB;" 2>$null
    docker compose -f "$Root\docker-compose.yml" exec -T postgres `
        psql -U $Env:POSTGRES_USER -c "CREATE DATABASE $Env:POSTGRES_DB;" 2>$null
}

# ── 9. Django migrations ──────────────────────────────────────────────────────
Log "Running Django migrations..."
Push-Location $ServerDir
python manage.py migrate --noinput
Pop-Location
Ok "Migrations applied."

# ── Helper: Start-Window ──────────────────────────────────────────────────────
# Opens a new PowerShell window and returns the Process object.
function Start-Window($title, $command) {
    $args = "-NoExit -Command `"& {$command}`""
    $proc = Start-Process powershell -ArgumentList "-NoExit -Command", $command `
                -WindowStyle Normal -PassThru
    return $proc
}

# ── 10. Django ASGI server ────────────────────────────────────────────────────
Log "Starting Django ASGI server on http://localhost:8000 ..."
$DjangoCmd = "cd '$ServerDir'; uvicorn andromeda.asgi:application --host 127.0.0.1 --port 8000 --reload --reload-dir '$ServerDir' --log-level info"
$DjangoProc = Start-Process powershell `
    -ArgumentList "-NoExit", "-Command", $DjangoCmd `
    -WindowStyle Normal -PassThru
$Jobs += $DjangoProc
Ok "Django started in new window (PID $($DjangoProc.Id))."

Start-Sleep -Seconds 2

# ── 11. Celery worker + beat ──────────────────────────────────────────────────
if (-not $NoCelery) {
    Log "Starting Celery worker..."
    $WorkerCmd = "cd '$ServerDir'; celery -A andromeda worker --loglevel=info --concurrency=2 -Q notifications,messages,default"
    $WorkerProc = Start-Process powershell `
        -ArgumentList "-NoExit", "-Command", $WorkerCmd `
        -WindowStyle Normal -PassThru
    $Jobs += $WorkerProc
    Ok "Celery worker started in new window (PID $($WorkerProc.Id))."

    Log "Starting Celery beat..."
    $BeatCmd = "cd '$ServerDir'; celery -A andromeda beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler"
    $BeatProc = Start-Process powershell `
        -ArgumentList "-NoExit", "-Command", $BeatCmd `
        -WindowStyle Normal -PassThru
    $Jobs += $BeatProc
    Ok "Celery beat started in new window (PID $($BeatProc.Id))."
}

# ── 12. Angular dev server ────────────────────────────────────────────────────
if (-not $NoClient) {
    Log "Starting Angular dev server on http://localhost:4200 ..."
    $NgCmd = "cd '$ClientDir'; npm start"
    $NgProc = Start-Process powershell `
        -ArgumentList "-NoExit", "-Command", $NgCmd `
        -WindowStyle Normal -PassThru
    $Jobs += $NgProc
    Ok "Angular started in new window (PID $($NgProc.Id))."
}

# ── 13. Summary ───────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "╔══════════════════════════════════════════════╗" -ForegroundColor Magenta
Write-Host "║        Andromeda is running locally          ║" -ForegroundColor Magenta
Write-Host "╠══════════════════════════════════════════════╣" -ForegroundColor Magenta
Write-Host "║  App          →  " -NoNewline -ForegroundColor Magenta
Write-Host "http://localhost:4200      " -NoNewline -ForegroundColor Green
Write-Host "║" -ForegroundColor Magenta
Write-Host "║  API          →  " -NoNewline -ForegroundColor Magenta
Write-Host "http://localhost:8000/api  " -NoNewline -ForegroundColor Green
Write-Host "║" -ForegroundColor Magenta
Write-Host "║  Admin        →  " -NoNewline -ForegroundColor Magenta
Write-Host "http://localhost:8000/admin" -NoNewline -ForegroundColor Green
Write-Host "║" -ForegroundColor Magenta
Write-Host "║  RabbitMQ UI  →  " -NoNewline -ForegroundColor Magenta
Write-Host "http://localhost:15672     " -NoNewline -ForegroundColor Green
Write-Host "║" -ForegroundColor Magenta
Write-Host "║  Neo4j UI     →  " -NoNewline -ForegroundColor Magenta
Write-Host "http://localhost:7474      " -NoNewline -ForegroundColor Green
Write-Host "║" -ForegroundColor Magenta
Write-Host "╚══════════════════════════════════════════════╝" -ForegroundColor Magenta
Write-Host ""
Write-Host "Close the spawned windows or press Ctrl+C here to stop everything." -ForegroundColor Yellow
Write-Host ""

# Wait – keep this window alive so cleanup runs on Ctrl+C
try {
    while ($true) { Start-Sleep -Seconds 5 }
} finally {
    Stop-All
}
