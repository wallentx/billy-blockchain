#!/bin/bash

set -o errexit

if [ ! "$1" ]; then
  echo "This script requires either amd64 of arm64 as an argument"
	exit 1
elif [ "$1" = "amd64" ]; then
	PLATFORM="amd64"
else
	PLATFORM="arm64"
fi
export PLATFORM

git status
git submodule

# If the env variable NOTARIZE and the username and password variables are
# set, this will attempt to Notarize the signed DMG

if [ ! "$CHIA_INSTALLER_VERSION" ]; then
	echo "WARNING: No environment variable CHIA_INSTALLER_VERSION set. Using 0.0.0."
	CHIA_INSTALLER_VERSION="0.0.0"
fi
echo "Chia Installer Version is: $CHIA_INSTALLER_VERSION"
export CHIA_INSTALLER_VERSION

echo "Installing npm and electron packagers"
cd npm_linux || exit 1
npm ci
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

# Creates a directory of licenses
echo "Building pip and NPM license directory"
pwd
bash ./build_license_directory.sh

cp -r dist/daemon ../chia-blockchain-gui/packages/gui

# Change to the gui package
cd ../chia-blockchain-gui/packages/gui || exit 1

# sets the version for chia-blockchain in package.json
cp package.json package.json.orig
jq --arg VER "$CHIA_INSTALLER_VERSION" '.version=$VER' package.json > temp.json && mv temp.json package.json

echo "Building Linux Flatpak Electron app"
PRODUCT_NAME="chia"
if [ "$PLATFORM" = "arm64" ]; then
  # electron-builder does not work for arm64 as of Aug 16, 2022.
  # This is a temporary fix.
  # https://github.com/jordansissel/fpm/issues/1801#issuecomment-919877499
  # @TODO Consolidates the process to amd64 if the issue of electron-builder is resolved
  sudo apt -y install ruby ruby-dev
  # `sudo gem install public_suffix -v 4.0.7` is required to fix the error below.
  #   ERROR:  Error installing fpm:
  #   The last version of public_suffix (< 6.0, >= 2.0.2) to support your Ruby & RubyGems was 4.0.7. Try installing it with `gem install public_suffix -v 4.0.7` and then running the current command again
  #   public_suffix requires Ruby version >= 2.6. The current ruby version is 2.5.0.
  # @TODO Maybe versions of sub dependencies should be managed by gem lock file.
  # @TODO Once ruby 2.6 can be installed on `apt install ruby`, installing public_suffix below should be removed.
  sudo gem install public_suffix -v 4.0.7
  sudo gem install fpm
  sudo apt -y install flatpak flatpak-builder
  echo USE_SYSTEM_FPM=true env DEBUG="@malept/flatpak-bundler" npx electron-builder build --linux flatpak --arm64 \
    --config.linux.desktop.Name="Chia Blockchain" \
    --config.artifactName="chia-blockchain"
  USE_SYSTEM_FPM=true npx electron-builder build --linux flatpak --arm64 \
    --config.linux.desktop.Name="Chia Blockchain" \
    --config.artifactName="chia-blockchain"
  LAST_EXIT_CODE=$?
else
  sudo apt -y install flatpak flatpak-builder
  echo DEBUG="@malept/flatpak-bundler" npx electron-builder build --linux flatpak --x64 \
    --config.linux.desktop.Name="Chia Blockchain" \
    --config.artifactName="chia-blockchain"
  DEBUG="@malept/flatpak-bundler" npx electron-builder build --linux flatpak --x64 \
    --config.linux.desktop.Name="Chia Blockchain" \
    --config.artifactName="chia-blockchain"
  LAST_EXIT_CODE=$?
fi
ls -l dist/linux*-unpacked/resources

# reset the package.json to the original
mv package.json.orig package.json

if [ "$LAST_EXIT_CODE" -ne 0 ]; then
	echo >&2 "electron-builder failed!"
	exit $LAST_EXIT_CODE
fi

GUI_FLATPAK_NAME=chia-blockchain_${CHIA_INSTALLER_VERSION}_${PLATFORM}.flatpak
mv "dist/chia-blockchain-${CHIA_INSTALLER_VERSION}.flatpak" "../../../build_scripts/dist/${GUI_FLATPAK_NAME}"
cd ../../../build_scripts || exit 1

echo "Create final installer"
rm -rf final_installer
mkdir final_installer

mv "dist/${GUI_FLATPAK_NAME}" final_installer/

ls -l final_installer/
