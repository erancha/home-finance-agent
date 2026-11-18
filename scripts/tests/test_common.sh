#!/usr/bin/env bash
# Verifies the settings and registry handling of scripts/common.sh: collect_missing_settings names
# every blank or still-placeholder setting with its file before require_collected_settings stops;
# compose exports both registries' content for docker compose, and stops naming init-env.sh when a
# registry is missing.
set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }

mkdir -p "$WORK/scripts/lib" "$WORK/backend" "$WORK/bin"
cp "$SCRIPTS_DIR/common.sh" "$WORK/scripts/"
cp "$SCRIPTS_DIR"/lib/{settings-guard.sh,ec2.sh,stack-params.sh} "$WORK/scripts/lib/"
for name in params secrets; do
  cp "$SCRIPTS_DIR/lib/$name.example.sh" "$WORK/scripts/lib/$name.sh"
done
# The copy is a git repository of its own, which ignores the settings files, so the settings guard
# admits them.
git -C "$WORK" init -q
git -C "$WORK" config core.hooksPath .githooks
printf '/scripts/lib/params.sh\n/scripts/lib/secrets.sh\n/bin/\n' > "$WORK/.gitignore"
# Stands in for Docker: prints the two registry variables compose hands to docker compose.
cat > "$WORK/bin/docker" <<'STUB'
#!/usr/bin/env bash
printf '%s|%s' "$CARD_AGENTS_REGISTRY" "$CARD_AGENTS_EC2_REGISTRY"
STUB
chmod +x "$WORK/bin/docker"
in_common() { (PATH="$WORK/bin:$PATH"; source "$WORK/scripts/common.sh"; "$@"); }

missing() {
  load_settings
  export LLM_MODEL="anthropic:claude-haiku-5-5" GOOGLE_CLIENT_ID="<client-id>"
  collect_missing_settings params.sh LLM_MODEL GOOGLE_CLIENT_ID
  collect_missing_settings secrets.sh LLM_API_KEY
  require_collected_settings
}
if in_common missing 2>"$WORK/err"; then fail "accepted blank settings"; fi
grep -q 'GOOGLE_CLIENT_ID (params.sh)' "$WORK/err" || fail "a placeholder was not named"
grep -q 'LLM_API_KEY (secrets.sh)' "$WORK/err" || fail "a blank setting was not named"
grep -q 'LLM_MODEL' "$WORK/err" && fail "a filled-in setting was named"

if in_common compose ps 2>"$WORK/err"; then fail "ran compose without the registries"; fi
grep -q 'backend/card-agents.yaml not found.*init-env.sh' "$WORK/err" \
  || fail "a missing registry does not name init-env.sh"
printf 'agents: [local]\n' > "$WORK/backend/card-agents.yaml"
printf 'agents: [ec2]\n' > "$WORK/backend/card-agents.ec2.yaml"
[ "$(in_common compose ps)" = "agents: [local]|agents: [ec2]" ] \
  || fail "compose did not export both registries"

echo "test_common: all checks passed"
