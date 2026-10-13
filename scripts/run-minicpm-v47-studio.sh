#!/bin/sh
# Launch Studio with the same MiniCPM checkpoint as TeXada Math Agent.
# Credentials must come from the process environment; never source .env here.
set -eu

if [ -z "${VLM_API_KEY:-${TEXADA_OPENAI_API_KEY:-}}" ]; then
    printf '%s\n' 'Set VLM_API_KEY (or TEXADA_OPENAI_API_KEY) in your environment before starting the MiniCPM profile.' >&2
    printf '%s\n' 'For an unauthenticated local server, use a non-secret placeholder such as local-no-key.' >&2
    exit 2
fi
if [ -z "${DEMO_TOKEN:-}" ]; then
    printf '%s\n' 'Set DEMO_TOKEN in your environment before starting Studio.' >&2
    exit 2
fi

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo_dir"

# Override the legacy model defaults when explicitly selecting this profile.
export VLM_MODEL=MiniCPM-V-4.7-1B
export VLM_BASE_URL="${VLM_BASE_URL:-https://api.modelbest.cn/v1}"
export VLM_API_KEY="${VLM_API_KEY:-${TEXADA_OPENAI_API_KEY:-}}"
export SKILL_MODE="${SKILL_MODE:-on}"

exec "${TEXADA_STUDIO_PYTHON:-python3}" -m uvicorn app:app --host 127.0.0.1 --port 8888 --app-dir webui "$@"
