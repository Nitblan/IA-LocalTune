!/usr/bin/bash
# ─────────────────────────────────────────────
# LocalTune Installer (Python + dependencias)
# ─────────────────────────────────────────────

set -e

echo "Instalando dependencias para LocalTune..."

# Gestor de paquetes
if command -v apt >/dev/null 2>&1; then
    PKG_MANAGER="apt"
elif command -v pacman >/dev/null 2>&1; then
    PKG_MANAGER="pacman"
elif command -v dnf >/dev/null 2>&1; then
    PKG_MANAGER="dnf"
else
    echo "❌ No se detectó un gestor de paquetes compatible"
    exit 1
fi

echo "📦 Usando gestor: $PKG_MANAGER"

# ─────────────────────────────────────────────
# Dependencias del sistema (pygame/audio/tkinter)
# ─────────────────────────────────────────────

if [ "$PKG_MANAGER" = "apt" ]; then
    sudo apt update
    sudo apt install -y \
        python3 python3-pip python3-venv \
        python3-tk \
        libasound2-dev \
        libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev \
        libportmidi-dev \
        libfreetype6-dev libjpeg-dev build-essential

elif [ "$PKG_MANAGER" = "pacman" ]; then
    sudo pacman -Syu --noconfirm \
        python python-pip tk \
        sdl2 sdl2_image sdl2_mixer sdl2_ttf \
        portmidi freetype2 libjpeg-turbo base-devel

elif [ "$PKG_MANAGER" = "dnf" ]; then
    sudo dnf install -y \
        python3 python3-pip python3-tkinter \
        SDL2 SDL2_image SDL2_mixer SDL2_ttf \
        portmidi-devel freetype-devel libjpeg-devel \
        gcc gcc-c++ make
fi

# ─────────────────────────────────────────────
# Entorno virtual (recomendado)
# ─────────────────────────────────────────────

echo "Creando entorno virtual..."

python3 -m venv .venv

source .venv/bin/activate

# ─────────────────────────────────────────────
# Actualizar pip
# ─────────────────────────────────────────────

pip install --upgrade pip setuptools wheel

# ─────────────────────────────────────────────
# Instalar librerías Python
# ─────────────────────────────────────────────

echo "Instalando librerías Python..."

pip install pygame mutagen pillow

# ─────────────────────────────────────────────
# Final
# ─────────────────────────────────────────────

echo ""
echo " Instalación completada"
echo " Activa el entorno con:"
echo "   source .venv/bin/activate"
echo ""
echo " Ejecuta tu programa con:"
echo "   python L0calT8ne.py"
















