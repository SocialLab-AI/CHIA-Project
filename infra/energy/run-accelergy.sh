#!/bin/sh
set -eu

# Accelergy 0.3 and its McPAT plug-in write configuration, generated XML, and
# cache files beside their configured plug-ins. Stage those read-only image
# assets in an isolated directory so the container can remain unprivileged.
runtime_root="$(mktemp -d /tmp/chia-accelergy.XXXXXX)"
plugin_root="$runtime_root/estimation_plug_ins"
runtime_home="$runtime_root/home"

mkdir -p "$plugin_root" "$runtime_home/.config/accelergy"
cp -R /opt/energy-venv/share/accelergy/estimation_plug_ins/. "$plugin_root/"

cat >"$runtime_home/.config/accelergy/accelergy_config.yaml" <<EOF
version: 0.3
estimator_plug_ins:
  - $plugin_root
primitive_components:
  - /opt/energy-venv/share/accelergy/primitive_component_libs
compound_components: []
EOF

export HOME="$runtime_home"
exec accelergy "$@"
