#!/usr/bin/env bash
# Vidora: one-command deploy for a clean Ubuntu 22.04 / 24.04.
#
#   git clone <repo> vidora && cd vidora && ./deploy.sh --demo
#
# Options:
#   --demo                 fill the database with demo users, videos and comments
#   --domain NAME --email  real domain with a Let's Encrypt certificate (otherwise self-signed)
#   --skip-install         do not try to install Docker (it must already be there)
#
# Idempotent: re-running keeps secrets and data, rebuilds and restarts what changed.
# Env: VIDORA_HIDE_SECRETS=1 hides passwords in the final summary (CI logs are public).
set -Eeuo pipefail

cd "$(dirname "$0")"

DEMO=false
DOMAIN=""
EMAIL=""
SKIP_INSTALL=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --demo) DEMO=true; shift ;;
    --domain) DOMAIN="${2:-}"; shift 2 ;;
    --email) EMAIL="${2:-}"; shift 2 ;;
    --skip-install) SKIP_INSTALL=true; shift ;;
    -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1 (see ./deploy.sh --help)" >&2; exit 2 ;;
  esac
done

c_green=$'\e[32m'; c_red=$'\e[31m'; c_yellow=$'\e[33m'; c_reset=$'\e[0m'
step() { echo "${c_green}==>${c_reset} $*"; }
warn() { echo "${c_yellow}warning:${c_reset} $*" >&2; }
die() { echo "${c_red}error:${c_reset} $*" >&2; exit 1; }
trap 'echo "${c_red}deploy failed:${c_reset} $BASH_COMMAND (line $LINENO). Logs: docker compose logs --tail=100" >&2' ERR

SUDO=""
if [[ $EUID -ne 0 ]]; then
  command -v sudo >/dev/null || die "run as root or install sudo"
  SUDO="sudo"
fi

# ---------------------------------------------------------------- 1. system checks
if [[ -r /etc/os-release ]]; then
  . /etc/os-release
  [[ "${ID:-}" == "ubuntu" ]] || warn "tested on Ubuntu 22.04/24.04, this is ${PRETTY_NAME:-unknown}"
fi
mem_mb=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo 2>/dev/null || echo 0)
(( mem_mb == 0 || mem_mb >= 1800 )) || warn "only ${mem_mb} MB RAM, 2 GB+ recommended"
disk_gb=$(df -Pk . | awk 'NR==2 {print int($4/1024/1024)}')
(( disk_gb >= 5 )) || die "need at least 5 GB free disk space, have ${disk_gb} GB"

# ---------------------------------------------------------------- 2. docker
# Network hiccups are common on fresh VMs: every download is retried.
retry() { # retry <attempts> <command...>
  local n=$1 i; shift
  for ((i = 1; i <= n; i++)); do
    "$@" && return 0
    ((i < n)) && { warn "attempt $i/$n failed: $*; retrying in $((i * 5))s"; sleep $((i * 5)); }
  done
  return 1
}
APT=($SUDO apt-get -o Acquire::Retries=5 -o Acquire::http::Timeout=30)

install_docker() {
  step "Installing Docker Engine from the official apt repository"
  retry 3 "${APT[@]}" update -qq
  retry 3 "${APT[@]}" install -y -qq ca-certificates curl openssl >/dev/null
  $SUDO install -m 0755 -d /etc/apt/keyrings
  retry 3 $SUDO curl -fsSL --retry 5 https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  $SUDO chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME:-$(lsb_release -cs)} stable"     | $SUDO tee /etc/apt/sources.list.d/docker.list >/dev/null
  retry 3 "${APT[@]}" update -qq
  retry 3 "${APT[@]}" install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin >/dev/null
}

start_docker() {
  if [[ -d /run/systemd/system ]]; then
    $SUDO systemctl enable --now docker >/dev/null
  else # containers / WSL without systemd
    $SUDO sh -c 'nohup dockerd >/var/log/dockerd.log 2>&1 &'
  fi
  for _ in $(seq 1 30); do $SUDO docker info >/dev/null 2>&1 && return 0; sleep 1; done
  die "Docker daemon did not start (see /var/log/dockerd.log or journalctl -u docker)"
}

if ! command -v docker >/dev/null 2>&1; then
  $SKIP_INSTALL && die "docker not found and --skip-install given"
  command -v apt-get >/dev/null || die "docker not found and this is not an apt-based system"
  install_docker
fi
$SUDO docker info >/dev/null 2>&1 || start_docker

# Use docker without sudo if the current user is allowed to.
if docker info >/dev/null 2>&1; then DOCKER=(docker); else DOCKER=($SUDO docker); fi
"${DOCKER[@]}" compose version >/dev/null 2>&1 || die "docker compose v2 plugin is missing (apt-get install docker-compose-plugin)"
# Small tools the script relies on (minimal images may lack them).
missing=()
for tool in curl; do command -v "$tool" >/dev/null || missing+=("$tool"); done
if ((${#missing[@]})); then
  command -v apt-get >/dev/null || die "please install: ${missing[*]}"
  retry 3 "${APT[@]}" update -qq && retry 3 "${APT[@]}" install -y -qq "${missing[@]}" >/dev/null
fi

compose() { "${DOCKER[@]}" compose "$@"; }

# ---------------------------------------------------------------- 3. ports
port_busy() { # port is taken by something that is not our caddy container
  local p=$1
  command -v ss >/dev/null || return 1
  ss -ltnH "sport = :$p" 2>/dev/null | grep -q . || return 1
  compose ps --status running web 2>/dev/null | grep -q web && return 1
  return 0
}
for p in 80 443; do
  port_busy "$p" && die "port $p is already in use by another program (ss -ltnp 'sport = :$p')"
done

# ---------------------------------------------------------------- 4. secrets
step "Preparing .env (secrets are generated once and kept)"
if [[ -n "$DOMAIN" ]]; then
  [[ -n "$EMAIL" ]] || die "--domain needs --email for Let's Encrypt"
  bash scripts/gen_env.sh --domain "$DOMAIN" --email "$EMAIL"
else
  bash scripts/gen_env.sh
fi
env_get() { grep -E "^$1=" .env | head -1 | cut -d= -f2-; }

# ---------------------------------------------------------------- 5. build and start
step "Building images (first run takes a few minutes)"
retry 3 compose build --pull  # base images and packages come from the network

step "Starting services"
compose up -d --remove-orphans

step "Waiting for the app to become ready"
ready=false
for _ in $(seq 1 90); do
  if curl -ksf --resolve localhost:443:127.0.0.1 https://localhost/api/v1/health/ready >/dev/null 2>&1; then
    ready=true; break
  fi
  sleep 2
done
$ready || { compose ps; die "app is not ready after 3 minutes, see: docker compose logs --tail=100 api web"; }

# ---------------------------------------------------------------- 6. accounts and demo data
# Admin/demo passwords are handed only to these one-off containers (-e NAME takes the value
# from this shell), never to the long-running api/worker.
export ADMIN_USERNAME ADMIN_EMAIL ADMIN_PASSWORD DEMO_PASSWORD
ADMIN_USERNAME="$(env_get ADMIN_USERNAME)"
ADMIN_EMAIL="$(env_get ADMIN_EMAIL)"
ADMIN_PASSWORD="$(env_get ADMIN_PASSWORD)"
DEMO_PASSWORD="$(env_get DEMO_PASSWORD)"

step "Creating the admin account (if missing)"
compose run --rm --no-deps -T -e ADMIN_USERNAME -e ADMIN_EMAIL -e ADMIN_PASSWORD api python -m app.scripts.create_admin

if $DEMO; then
  step "Loading demo data (14 videos are generated and transcoded with ffmpeg, takes 2-5 minutes)"
  compose run --rm --no-deps -T -e DEMO_PASSWORD worker python -m app.scripts.seed
fi

# ---------------------------------------------------------------- 7. summary
ips=$(hostname -I 2>/dev/null | tr ' ' '\n' | grep -E '^[0-9]+\.' | head -3 | tr '\n' ' ')
show() { if [[ "${VIDORA_HIDE_SECRETS:-0}" == "1" ]]; then echo "<hidden, see .env>"; else env_get "$1"; fi; }

echo
echo "${c_green}Vidora is up.${c_reset}"
if [[ -n "$DOMAIN" ]]; then
  echo "  Open:     https://$DOMAIN"
else
  echo "  Open:     https://localhost  or  https://<server-ip>   (${ips:-ip not detected})"
  echo "            The certificate is self-signed: accept the browser warning once."
fi
echo "  API docs: /docs"
echo "  Admin:    login '$(env_get ADMIN_USERNAME)'  password: $(show ADMIN_PASSWORD)"
if $DEMO; then
  echo "  Demo:     logins 'moderator', 'alice', 'bob', 'carol', 'dave'  password: $(show DEMO_PASSWORD)"
fi
echo "  Check the full scenario: python3 scripts/e2e.py"
