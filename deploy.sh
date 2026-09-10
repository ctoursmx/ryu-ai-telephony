#!/usr/bin/env bash
# ==============================================================================
# SCRIPT DE DESPLIEGUE AUTOMÁTICO 1-CLICK (Bash / Linux / Mac / Git Bash)
# Restaurante Ryu AI Telephony -> Oracle Cloud VPS (140.84.186.64)
# ==============================================================================
set -e

BRANCH="${1:-main}"
SSH_KEY="${HOME}/.ssh/ryu_oracle.key"
VPS_HOST="ubuntu@140.84.186.64"
VPS_DIR="/home/ubuntu/ryu-ai-telephony"

echo "========================================================"
echo "   🚀 INICIANDO DESPLIEGUE A ORACLE CLOUD VPS"
echo "   Servidor: $VPS_HOST | Rama: $BRANCH"
echo "========================================================"

if [ ! -f "$SSH_KEY" ]; then
    echo "❌ Error: No se encontró la clave SSH en $SSH_KEY"
    exit 1
fi

if [ -n "$(git status --porcelain)" ]; then
    echo "📝 Guardando cambios locales..."
    git add .
    git commit -m "actualizacion de despliegue automatico"
fi

echo "⬆️  Sincronizando con GitHub (Rama $BRANCH)..."
git push origin "$BRANCH"

echo "🌐 Desplegando en Oracle Cloud VPS por SSH..."
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$VPS_HOST" "
set -e
cd $VPS_DIR
git fetch origin
git checkout $BRANCH
git pull origin $BRANCH
docker compose up -d --force-recreate ryu-telephony
sleep 8
docker logs --tail 20 ryu-telephony-service
"

echo "========================================================"
echo "   🎉 DESPLIEGUE COMPLETADO Y EN VIVO EXITOSAMENTE"
echo "   📞 Prueba llamando al: 33 8526 1250"
echo "========================================================"
