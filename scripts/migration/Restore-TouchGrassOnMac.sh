#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/migration/Restore-TouchGrassOnMac.sh BUNDLE.zip [options]

Options:
  --compose-file FILE   Compose file to use (default: docker-compose.dev.yml)
  --replace-existing    Allow pg_restore to replace existing database objects
  --replace-config      Replace an existing .env with the bundle's private .env
  --no-start            Do not start the complete stack after restoration
EOF
}

if [[ $# -lt 1 ]]; then
  usage
  exit 2
fi

bundle="$1"
shift
compose_file="docker-compose.dev.yml"
replace_existing=false
replace_config=false
start_stack=true

while [[ $# -gt 0 ]]; do
  case "$1" in
    --compose-file)
      compose_file="$2"
      shift 2
      ;;
    --replace-existing)
      replace_existing=true
      shift
      ;;
    --replace-config)
      replace_config=true
      shift
      ;;
    --no-start)
      start_stack=false
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 2
      ;;
  esac
done

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

command -v docker >/dev/null || { echo "Docker is required." >&2; exit 1; }
command -v unzip >/dev/null || { echo "unzip is required." >&2; exit 1; }
docker info >/dev/null

[[ -f "$bundle" ]] || { echo "Bundle not found: $bundle" >&2; exit 1; }
[[ -f "$compose_file" ]] || { echo "Compose file not found: $compose_file" >&2; exit 1; }

stamp="$(date +%Y%m%d-%H%M%S)"
restore_root="$repo_root/.migration-restore/$stamp"
mkdir -p "$restore_root"
unzip -q "$bundle" -d "$restore_root"

stage="$(find "$restore_root" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
[[ -n "$stage" && -f "$stage/manifest.json" ]] || { echo "Invalid TouchGrass migration bundle." >&2; exit 1; }
[[ -f "$stage/touchgrass-postgres.dump" ]] || { echo "Database dump is missing." >&2; exit 1; }

if [[ -f "$stage/private/.env" ]]; then
  if [[ ! -f .env || "$replace_config" == true ]]; then
    cp "$stage/private/.env" .env
    chmod 600 .env
    echo "Restored private .env. Review Windows paths before starting the stack."
  else
    echo "Existing .env preserved. Use --replace-config only if replacement is intentional."
  fi
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  chmod 600 .env
  echo "Created .env from .env.example. Edit its passwords, keys, and ICLOUD_PHOTOS_ROOT, then rerun this command." >&2
  exit 3
fi

if grep -Eq '^(POSTGRES_PASSWORD|SECRET_KEY)=changeme123([[:space:]]|$)' .env; then
  echo ".env still contains example database/application secrets. Replace them before restoring." >&2
  exit 3
fi

if grep -Eq '^ICLOUD_PHOTOS_ROOT=[A-Za-z]:/' .env; then
  echo ".env still contains a Windows ICLOUD_PHOTOS_ROOT. Point it at an empty Mac directory such as $repo_root/.local/icloud-photos before restoring." >&2
  exit 3
fi

mkdir -p .local/icloud-photos

echo "Starting the database..."
docker compose -f "$compose_file" up -d db
db_id="$(docker compose -f "$compose_file" ps -q db)"
[[ -n "$db_id" ]] || { echo "Database container did not start." >&2; exit 1; }

for _ in {1..60}; do
  if docker compose -f "$compose_file" exec -T db sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
docker compose -f "$compose_file" exec -T db sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null

docker cp "$stage/touchgrass-postgres.dump" "${db_id}:/tmp/touchgrass-postgres.dump"
restore_args=(--no-owner --no-privileges)
if [[ "$replace_existing" == true ]]; then
  restore_args+=(--clean --if-exists)
fi
quoted_restore_args="${restore_args[*]}"
if ! docker compose -f "$compose_file" exec -T db sh -lc "PGPASSWORD=\"\$POSTGRES_PASSWORD\" pg_restore -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" $quoted_restore_args /tmp/touchgrass-postgres.dump"; then
  echo "Database restore failed. If this is not a fresh database and replacement is intentional, rerun with --replace-existing." >&2
  exit 1
fi
docker compose -f "$compose_file" exec -T db rm -f /tmp/touchgrass-postgres.dump

echo "Starting the backend to restore media..."
docker compose -f "$compose_file" up -d server
server_id="$(docker compose -f "$compose_file" ps -q server)"
[[ -n "$server_id" ]] || { echo "Backend container did not start." >&2; exit 1; }

if [[ -f "$stage/touchgrass-media.tar.gz" ]]; then
  docker cp "$stage/touchgrass-media.tar.gz" "${server_id}:/tmp/touchgrass-media.tar.gz"
  docker compose -f "$compose_file" exec -T server sh -lc 'tar -xzf /tmp/touchgrass-media.tar.gz -C /code/media && rm -f /tmp/touchgrass-media.tar.gz'
fi

if [[ -f "$stage/touchgrass-uat-artifacts.tar.gz" ]]; then
  tar -xzf "$stage/touchgrass-uat-artifacts.tar.gz" -C "$repo_root"
  echo "Restored ignored UAT evidence."
fi

docker compose -f "$compose_file" exec -T server python manage.py migrate --noinput

if [[ "$start_stack" == true ]]; then
  docker compose -f "$compose_file" up -d --build
fi

echo ""
echo "TouchGrass restore complete."
echo "Review .env, especially ICLOUD_PHOTOS_ROOT, before relying on photo features."
echo "Open http://localhost:8015 and follow documentation/docs/development/macos_setup.md."
