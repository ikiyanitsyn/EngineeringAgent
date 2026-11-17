#!/usr/bin/env bash
# Install CalculiX + the libraries Gmsh needs on a GitHub Ubuntu runner.
# Uses .deb files cached in ~/solver-debs when present (no package server needed), otherwise
# apt with time limits and retries, then keeps the downloaded .deb files for the cache.
set -u
D="$HOME/solver-debs"
PKGS="calculix-ccx libglu1-mesa libgl1 libxrender1 libxcursor1 libxft2 libxinerama1"
if ls "$D"/*.deb >/dev/null 2>&1 && sudo dpkg -i --skip-same-version "$D"/*.deb >/dev/null 2>&1 && command -v ccx >/dev/null; then
  echo "solver installed from the cached packages"; exit 0
fi
for i in 1 2 3; do
  sudo timeout 240 apt-get -o Acquire::Retries=3 -o Acquire::http::Timeout=30 update -qq &&
  sudo timeout 300 apt-get -o Acquire::Retries=3 -o APT::Keep-Downloaded-Packages=true install -y -qq $PKGS && break
  echo "package install attempt $i failed; retrying"; sleep 10
done
command -v ccx >/dev/null || { echo "CalculiX could not be installed"; exit 1; }
mkdir -p "$D" && cp /var/cache/apt/archives/*.deb "$D"/ 2>/dev/null || true
echo "solver installed from the package server ($(ls "$D" | wc -l) packages kept for the cache)"
