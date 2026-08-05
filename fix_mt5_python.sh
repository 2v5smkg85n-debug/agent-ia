#!/bin/bash
# Corrige l'installation: installe Python Windows via Wine pour le package MetaTrader5
set -e

echo "=== Installation Python Windows + MetaTrader5 ==="

# 1. Telecharger Python 3.12 pour Windows
echo "[1/4] Telechargement Python 3.12 Windows..."
cd /tmp
wget -q "https://www.python.org/ftp/python/3.12.3/python-3.12.3-amd64.exe" -O python-win.exe

# 2. Installer Python dans Wine
echo "[2/4] Installation Python Windows via Wine..."
export WINEPREFIX=~/.mt5
export WINEDEBUG=-all
WINEPREFIX=~/.mt5 wine python-win.exe /quiet InstallAllUsers=1 PrependPath=1 Include_pip=1 2>/dev/null || true

# 3. Installer le package MetaTrader5 via Wine Python
echo "[3/4] Installation MetaTrader5 package..."
PYTHON_WIN="$HOME/.mt5/drive_c/Program Files/Python312/python.exe"
if [ ! -f "$PYTHON_WIN" ]; then
    PYTHON_WIN="$HOME/.mt5/drive_c/users/$USER/Local Settings/Application Data/Programs/Python/Python312/python.exe"
fi
if [ ! -f "$PYTHON_WIN" ]; then
    # Chercher python.exe
    PYTHON_WIN=$(find ~/.mt5/drive_c -name "python.exe" -type f 2>/dev/null | head -1)
fi

if [ -z "$PYTHON_WIN" ]; then
    echo "ERREUR: Python Windows non trouve. Essayons une alternative..."
    # Alternative: installer via pip dans le venv Linux avec --platform
    cd ~/agent-ia
    source venv/bin/activate
    pip install MetaTrader5 --platform win_amd64 --only-binary :all: 2>/dev/null || \
    pip install MetaTrader5 --no-deps 2>/dev/null || \
    echo "Le package MetaTrader5 nécessite Python Windows"
    echo ""
    echo "SOLUTION ALTERNATIVE: Utiliser l'API HTTP de MT5"
    echo "Le terminal MT5 expose une API locale accessible via Wine"
    exit 0
fi

echo "Python Windows trouve: $PYTHON_WIN"
WINEPREFIX=~/.mt5 wine "$PYTHON_WIN" -m pip install MetaTrader5 2>&1 | tail -5

# 4. Tester
echo "[4/4] Test connexion..."
WINEPREFIX=~/.mt5 wine "$PYTHON_WIN" -c "import MetaTrader5 as mt5; print('MetaTrader5 version:', mt5.__version__)" 2>&1

echo ""
echo "=== Installation terminee ==="
echo "Python Windows: $PYTHON_WIN"
echo "Pour utiliser le pont MT5:"
echo "  export MT5_PYTHON=\"$PYTHON_WIN\""
