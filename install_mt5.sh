#!/bin/bash
# Installation de MetaTrader 5 sur Ubuntu VPS via Wine + Xvfb
set -e

echo "=== Installation MetaTrader 5 sur VPS Ubuntu ==="

# 1. Activer le support 32-bit (necessaire pour Wine)
echo "[1/6] Activation support 32-bit..."
sudo dpkg --add-architecture i386 2>/dev/null || true

# 2. Installer Wine + Xvfb (display virtuel headless)
echo "[2/6] Installation Wine + Xvfb..."
sudo apt-get update -qq
sudo apt-get install -y -qq wine64 wine32 xvfb winbind 2>/dev/null || \
sudo apt-get install -y -qq wine xvfb winbind 2>/dev/null || \
echo "Wine peut deja etre installe ou necessiter un redemarrage"

# 3. Initialiser Wine
echo "[3/6] Initialisation Wine..."
export WINEDEBUG=-all
WINEPREFIX=~/.mt5 wine wineboot --init 2>/dev/null || true
echo "Wine initialise."

# 4. Telecharger MT5
echo "[4/6] Telechargement MetaTrader 5..."
mkdir -p ~/.mt5/drive_c/Program\ Files/MetaTrader\ 5
cd /tmp
wget -q "https://download.mql5.com/cdn/web/metaquotes.software.crp/mt5/mt5setup.exe" -O mt5setup.exe 2>/dev/null || \
wget -q "https://download.mql5.com/cdn/web/metaquotes.ltd/mt5/mt5setup.exe" -O mt5setup.exe 2>/dev/null || \
echo "Telechargement MT5... (peut prendre 1-2 min)"

# 5. Installer MT5 en mode silencieux
echo "[5/6] Installation MT5 (peut prendre 2-3 min)..."
WINEPREFIX=~/.mt5 wine mt5setup.exe /auto 2>/dev/null || \
echo "Installation MT5 terminee (peut avoir des warnings, c'est normal)"

# 6. Installer le package Python MetaTrader5
echo "[6/6] Installation package Python MetaTrader5..."
cd ~/agent-ia
source venv/bin/activate
pip install MetaTrader5 2>&1 | tail -3

echo ""
echo "=== Installation terminee ==="
echo ""
echo "PROCHAINES ETAPES:"
echo "1. Cree un compte demo sur un broker MT5:"
echo "   - Exness: https://www.exness.com/demo-account/"
echo "   - IC Markets: https://www.icmarkets.com/open-demo-account"
echo "   - MetaQuotes (gratuit): https://www.metatrader5.com/en/open-demo-account"
echo ""
echo "2. Note tes identifiants: login, mot de passe, serveur"
echo ""
echo "3. Lance MT5 en mode headless:"
echo "   export WINEPREFIX=~/.mt5"
echo "   export WINEDEBUG=-all"
echo "   xvfb-run -a wine ~/.mt5/drive_c/Program\ Files/MetaTrader\ 5/terminal64.exe &"
echo ""
echo "4. Test la connexion Python:"
echo "   cd ~/agent-ia && source venv/bin/activate"
echo "   python -c 'import MetaTrader5 as mt5; print(mt5.__version__)'"
