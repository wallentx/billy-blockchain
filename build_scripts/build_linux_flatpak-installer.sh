#!/usr/bin/env bash

set -o errexit

if [ ! "$1" ]; then
  echo "This script requires either amd64 or arm64 as an argument"
  exit 1
elif [ "$1" = "amd64" ]; then
  PLATFORM="amd64"
  ELECTRON_BUILDER_ARCH="--x64"
else
  PLATFORM="arm64"
  ELECTRON_BUILDER_ARCH="--arm64"
fi
export PLATFORM

git status
git submodule

if [ ! "$CHIA_INSTALLER_VERSION" ]; then
  echo "WARNING: No environment variable CHIA_INSTALLER_VERSION set. Using 0.0.0."
  CHIA_INSTALLER_VERSION="0.0.0"
fi
echo "Chia Installer Version is: $CHIA_INSTALLER_VERSION"
export CHIA_INSTALLER_VERSION

echo "Installing npm and electron packagers"
cd npm_linux || exit 1
npm ci
NPM_PATH="$(pwd)/node_modules/.bin"
cd .. || exit 1

echo "Create dist/"
rm -rf dist
mkdir dist

echo "Create executables with pyinstaller"
SPEC_FILE=$(python -c 'import sys; from pathlib import Path; path = Path(sys.argv[1]); print(path.absolute().as_posix())' "pyinstaller.spec")
pyinstaller --log-level=INFO "$SPEC_FILE"
LAST_EXIT_CODE=$?
if [ "$LAST_EXIT_CODE" -ne 0 ]; then
  echo >&2 "pyinstaller failed!"
  exit $LAST_EXIT_CODE
fi

echo "Building pip and NPM license directory"
bash ./build_license_directory.sh

cp -r dist/daemon ../chia-blockchain-gui/packages/gui

cd ../chia-blockchain-gui/packages/gui || exit 1

cp package.json package.json.orig
jq --arg VER "$CHIA_INSTALLER_VERSION" '.version=$VER' package.json >temp.json && mv temp.json package.json

echo "Install Flatpak tooling"
sudo apt-get update -y
sudo apt-get install -y flatpak flatpak-builder
sudo flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
sudo flatpak install -y --noninteractive flathub org.electronjs.Electron2.BaseApp//22.08
sudo flatpak install -y --noninteractive flathub org.freedesktop.Sdk//22.08
sudo flatpak install -y --noninteractive flathub org.freedesktop.Platform//22.08

# electron-builder versions bundled with the GUI expect glob >= 10 for flatpak packaging
npm install glob@latest

echo "Building Linux Flatpak Electron app"
PRODUCT_NAME="chia"
"${NPM_PATH}/electron-builder" build --linux flatpak "${ELECTRON_BUILDER_ARCH}" \
  --config.extraMetadata.name=chia-blockchain \
  --config.productName="${PRODUCT_NAME}" --config.linux.desktop.Name="Chia Blockchain" \
  --config ../../../build_scripts/electron-builder.json
LAST_EXIT_CODE=$?
find dist -maxdepth 1 -name 'linux*-unpacked' -print -exec ls -l {}/resources \;

mv package.json.orig package.json

if [ "$LAST_EXIT_CODE" -ne 0 ]; then
  echo >&2 "electron-builder failed!"
  exit $LAST_EXIT_CODE
fi

GUI_FLATPAK_NAME="chia-blockchain_${CHIA_INSTALLER_VERSION}_${PLATFORM}.flatpak"
SOURCE_FLATPAK=$(find dist -maxdepth 1 -name '*.flatpak' -print -quit)
if [ -z "$SOURCE_FLATPAK" ]; then
  echo "Unable to locate generated flatpak package"
  exit 1
fi
mv "$SOURCE_FLATPAK" "../../../build_scripts/dist/${GUI_FLATPAK_NAME}"
cd ../../../build_scripts || exit 1

echo "Create final installer"
rm -rf final_installer
mkdir final_installer

mv "dist/${GUI_FLATPAK_NAME}" final_installer/

ls -l final_installer/
