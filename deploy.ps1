# ==============================================================================
# SCRIPT DE DESPLIEGUE AUTOMATICO 1-CLICK (PowerShell / Windows)
# Restaurante Ryu AI Telephony -> Oracle Cloud VPS (140.84.186.64)
# ==============================================================================

param (
    [string]$Branch = "main",
    [string]$CommitMsg = ""
)

$ErrorActionPreference = "Stop"
$SSH_KEY = "$HOME\.ssh\ryu_oracle.key"
$VPS_HOST = "ubuntu@140.84.186.64"
$VPS_DIR = "/home/ubuntu/ryu-ai-telephony"

Write-Host "`n========================================================" -ForegroundColor Cyan
Write-Host "   INICIANDO DESPLIEGUE A ORACLE CLOUD VPS" -ForegroundColor Cyan
Write-Host "   Servidor: $VPS_HOST | Rama: $Branch" -ForegroundColor Cyan
Write-Host "========================================================`n" -ForegroundColor Cyan

# 1. Verificar clave SSH local
if (-not (Test-Path $SSH_KEY)) {
    Write-Host "[ERROR] No se encontro la clave SSH en: $SSH_KEY" -ForegroundColor Red
    exit 1
}

# 2. Gestionar cambios locales de Git
$status = git status --porcelain
if ($status) {
    Write-Host "[GIT] Se detectaron cambios locales pendientes:" -ForegroundColor Yellow
    git status -s
    if (-not $CommitMsg) {
        $CommitMsg = Read-Host "`nIntroduce el mensaje de commit (o Enter para 'actualizacion de despliegue')"
        if (-not $CommitMsg) { $CommitMsg = "actualizacion de despliegue automatico" }
    }
    Write-Host "[GIT] Guardando cambios locales..." -ForegroundColor Yellow
    git add .
    git commit -m "$CommitMsg"
}

# 3. Subir cambios a GitHub
Write-Host "[GIT] Sincronizando con GitHub (Rama $Branch)..." -ForegroundColor Yellow
git push origin $Branch
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Fallo el push a GitHub." -ForegroundColor Red
    exit 1
}
Write-Host "[OK] Codigo sincronizado con GitHub." -ForegroundColor Green

# 4. Desplegar en la VPS por SSH
Write-Host "`n[VPS] Conectando a Oracle Cloud VPS y actualizando servicios..." -ForegroundColor Yellow
$cmd = "cd $VPS_DIR && git fetch origin && git checkout $Branch && git pull origin $Branch && docker compose up -d --force-recreate ryu-telephony && sleep 8 && docker logs --tail 20 ryu-telephony-service"
ssh -i $SSH_KEY -o StrictHostKeyChecking=no $VPS_HOST $cmd

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n========================================================" -ForegroundColor Green
    Write-Host "   DESPLIEGUE COMPLETADO Y EN VIVO EXITOSAMENTE" -ForegroundColor Green
    Write-Host "   Prueba llamando al: 33 8526 1250" -ForegroundColor Green
    Write-Host "========================================================`n" -ForegroundColor Green
} else {
    Write-Host "`n[ERROR] Ocurrio un problema durante el despliegue en la VPS." -ForegroundColor Red
}
