#!/usr/bin/env bash
set -euo pipefail

for setting in PREFIX RESOURCE_GROUP UI_STORAGE GITHUB_REPOSITORY GITHUB_SHA \
  BANKROLL_DB_PASSWORD JOURNAL_DB_PASSWORD FOOTBALL_DATA_API_TOKEN; do
  if [[ -z "${!setting:-}" ]]; then
    printf 'Missing deployment setting: %s\n' "$setting" >&2
    exit 1
  fi
done

image_prefix="ghcr.io/$(printf '%s' "$GITHUB_REPOSITORY" | tr '[:upper:]' '[:lower:]')"
for service in bankroll journal; do
  image="$image_prefix-$service:$GITHUB_SHA"
  if ! docker buildx imagetools inspect "$image" >/dev/null 2>&1; then
    printf 'Cannot pull %s anonymously. Make its package public on GitHub, then rerun the deploy job.\n' "$image" >&2
    exit 1
  fi
done

ui_url="$(az storage account show --resource-group "$RESOURCE_GROUP" --name "$UI_STORAGE" \
  --query primaryEndpoints.web -o tsv)"
ui_origin="${ui_url%/}"
if [[ "$ui_origin" != https://* ]]; then
  printf 'The Azure Storage static website endpoint is missing.\n' >&2
  exit 1
fi

app_origin() {
  local host
  host="$(az containerapp show --resource-group "$RESOURCE_GROUP" --name "$PREFIX-$1" \
    --query properties.configuration.ingress.fqdn -o tsv)"
  if [[ -z "$host" ]]; then
    printf 'The %s Container App has no ingress hostname.\n' "$1" >&2
    return 1
  fi
  printf 'https://%s\n' "$host"
}

bankroll_url="$(app_origin bankroll)"
journal_url="$(app_origin journal)"

database_url_for() {
  python3 - "$1" <<'PY'
import os
import sys
from urllib.parse import quote

service = sys.argv[1]
prefix = os.environ["PREFIX"]
password = quote(os.environ[service.upper() + "_DB_PASSWORD"], safe="")
print(f"mssql://{service}_app:{password}@{prefix}-sql.database.windows.net:1433/{prefix}-{service}-db")
PY
}

deploy_service() {
  local service="$1" app port database_url encoded_password
  local -a secrets settings
  app="$PREFIX-$service"
  database_url="$(database_url_for "$service")"
  encoded_password="${database_url%%@*}"
  encoded_password="${encoded_password##*:}"
  printf '::add-mask::%s\n' "$database_url" "$encoded_password"
  secrets=("database-url=$database_url")
  settings=("DATABASE_URL=secretref:database-url" "UI_ORIGIN=$ui_origin"
    "APP_VERSION=$GITHUB_SHA" "PORT=8000")
  if [[ "$service" == journal ]]; then
    secrets+=("football-data-api-token=$FOOTBALL_DATA_API_TOKEN")
    settings+=("FOOTBALL_DATA_API_TOKEN=secretref:football-data-api-token"
      "BANKROLL_URL=$bankroll_url")
  fi

  az containerapp secret set --resource-group "$RESOURCE_GROUP" --name "$app" \
    --secrets "${secrets[@]}" -o none
  port="$(az containerapp show --resource-group "$RESOURCE_GROUP" --name "$app" \
    --query properties.configuration.ingress.targetPort -o tsv)"
  if [[ "$port" != 8000 ]]; then
    az containerapp ingress update --resource-group "$RESOURCE_GROUP" --name "$app" \
      --target-port 8000 -o none
  fi
  az containerapp update --resource-group "$RESOURCE_GROUP" --name "$app" \
    --image "$image_prefix-$service:$GITHUB_SHA" \
    --min-replicas 0 --max-replicas 1 --set-env-vars "${settings[@]}" -o none
}

check_health() {
  local origin="$1" attempt
  for attempt in {1..24}; do
    if curl --fail --silent --max-time 10 "$origin/health" |
      jq -e --arg version "$GITHUB_SHA" \
        '.status == "ok" and .db == "ok" and .version == $version' >/dev/null; then
      printf 'Healthy at %s (%s)\n' "$origin" "$GITHUB_SHA"
      return
    fi
    sleep 5
  done
  printf 'Timed out waiting for %s to serve the deployed commit.\n' "$origin" >&2
  return 1
}

deploy_service bankroll
check_health "$bankroll_url"
deploy_service journal
check_health "$journal_url"

publish_dir="$(mktemp -d)"
trap 'rm -rf -- "$publish_dir"' EXIT
cp -R ui/. "$publish_dir"
python3 - "$bankroll_url" "$journal_url" >"$publish_dir/config.js" <<'PY'
import json
import sys

config = {"bankrollUrl": sys.argv[1], "journalUrl": sys.argv[2]}
print("window.BETLEDGER_CONFIG = " + json.dumps(config) + ";")
PY
az storage blob upload-batch --account-name "$UI_STORAGE" --auth-mode key \
  --source "$publish_dir" --destination '$web' --overwrite true -o none
curl --fail --silent --show-error --max-time 20 "$ui_url" -o /dev/null
if ! curl --fail --silent --show-error --max-time 20 "$ui_origin/config.js" |
  cmp -s - "$publish_dir/config.js"; then
  printf 'The public UI is not serving the API configuration uploaded by this run.\n' >&2
  exit 1
fi
printf 'Static UI is live at %s\n' "$ui_url"
