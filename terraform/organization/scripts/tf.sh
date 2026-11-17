#!/bin/bash
# tf.sh — Terraform en CloudShell sin llenar el giga de $HOME.
#
#   bash terraform/organization/scripts/tf.sh plan
#   bash terraform/organization/scripts/tf.sh apply
#   bash terraform/organization/scripts/tf.sh destroy                         # al terminar cada sesión de trabajo
#
# El proveedor de AWS ocupa unos 850 MB descomprimido: en el $HOME de CloudShell (1 GB) no
# entra. Así que el binario va a ~/bin (90 MB, persiste) y el proveedor a /tmp, que no persiste
# pero tiene lugar: cada sesión nueva lo vuelve a bajar en el init (un minuto).
set -euo pipefail
VERSION_TF=1.16.5
DIR=$(cd "$(dirname "$0")/.." && pwd)

if ! command -v terraform >/dev/null 2>&1 && [ ! -x "$HOME/bin/terraform" ]; then
  echo "instalando terraform $VERSION_TF en ~/bin…"
  mkdir -p "$HOME/bin"
  curl -sSL -o /tmp/terraform.zip \
    "https://releases.hashicorp.com/terraform/${VERSION_TF}/terraform_${VERSION_TF}_linux_amd64.zip"
  unzip -o -q /tmp/terraform.zip terraform -d "$HOME/bin"
  rm -f /tmp/terraform.zip
fi
TF=$(command -v terraform || echo "$HOME/bin/terraform")

export TF_DATA_DIR=/tmp/ateneo-tf
export TF_PLUGIN_CACHE_DIR=/tmp/ateneo-tf-cache
mkdir -p "$TF_PLUGIN_CACHE_DIR"

[ -f "$DIR/backend.hcl" ] || {
  echo "Falta terraform/organization/backend.hcl. Corré primero: bash terraform/organization/scripts/bootstrap-estado.sh" >&2
  exit 1
}
if [ ! -d "$TF_DATA_DIR/providers" ]; then
  "$TF" -chdir="$DIR" init -input=false -backend-config=backend.hcl
fi
exec "$TF" -chdir="$DIR" "$@"
