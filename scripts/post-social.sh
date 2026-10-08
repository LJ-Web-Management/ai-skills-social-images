#!/usr/bin/env bash
# Posts newly added images to Instagram and a Facebook Page via the Meta Graph API.
#
# Usage: scripts/post-social.sh images/ai-skills-2026-10-08.jpg [more images...]
#
# Required environment (set as GitHub Actions secrets, never committed):
#   META_ACCESS_TOKEN  Long-lived Facebook Page access token
#   IG_USER_ID         Instagram professional account ID
#   FB_PAGE_ID         Facebook Page ID
# Required environment (set by the workflow):
#   PAGES_BASE_URL     e.g. https://user.github.io/ai-skills-social-images
# Optional:
#   GRAPH_API_VERSION  default v23.0
#   DEFAULT_CAPTION    used when an image has no matching .txt caption file
#   POST_TO_INSTAGRAM  "false" to skip Instagram (default true)
#   POST_TO_FACEBOOK   "false" to skip Facebook (default true)
#   DRY_RUN            "true" to print what would be posted without calling the API

set -euo pipefail

GRAPH_API_VERSION="${GRAPH_API_VERSION:-v23.0}"
GRAPH="https://graph.facebook.com/${GRAPH_API_VERSION}"
POST_TO_INSTAGRAM="${POST_TO_INSTAGRAM:-true}"
POST_TO_FACEBOOK="${POST_TO_FACEBOOK:-true}"
DRY_RUN="${DRY_RUN:-false}"

die() { echo "::error::$*" >&2; exit 1; }

[[ $# -gt 0 ]] || die "No images given."
[[ -n "${PAGES_BASE_URL:-}" ]] || die "PAGES_BASE_URL is not set."
if [[ "$DRY_RUN" != "true" ]]; then
  [[ -n "${META_ACCESS_TOKEN:-}" ]] || die "Secret META_ACCESS_TOKEN is not set."
  [[ "$POST_TO_INSTAGRAM" == "false" || -n "${IG_USER_ID:-}" ]] || die "Secret IG_USER_ID is not set."
  [[ "$POST_TO_FACEBOOK" == "false" || -n "${FB_PAGE_ID:-}" ]] || die "Secret FB_PAGE_ID is not set."
fi

# Fails the run with the Graph API error message (never prints the token).
check_response() {
  local label="$1" body="$2"
  if jq -e '.error' >/dev/null 2>&1 <<<"$body"; then
    die "$label failed: $(jq -r '.error.message + " (code " + (.error.code|tostring) + ")"' <<<"$body")"
  fi
}

# Waits until the public URL serves the image itself, not an HTML 404 page.
wait_for_url() {
  local url="$1" headers status ctype
  for _ in $(seq 1 40); do
    headers="$(curl -sI "$url" || true)"
    status="$(awk 'NR==1{print $2}' <<<"$headers")"
    ctype="$(grep -i '^content-type:' <<<"$headers" | awk '{print $2}' | tr -d '\r')"
    if [[ "$status" == "200" && "$ctype" == image/* ]]; then
      echo "Live: $url ($ctype)"
      return 0
    fi
    echo "Waiting for $url (status=${status:-none}, type=${ctype:-none})..."
    sleep 15
  done
  die "Image never became available at $url"
}

post_instagram() {
  local url="$1" caption="$2" resp container status
  resp="$(curl -sS -X POST "${GRAPH}/${IG_USER_ID}/media" \
    --data-urlencode "image_url=${url}" \
    --data-urlencode "caption=${caption}" \
    --data-urlencode "access_token=${META_ACCESS_TOKEN}")"
  check_response "Instagram container" "$resp"
  container="$(jq -r '.id' <<<"$resp")"

  for _ in $(seq 1 30); do
    resp="$(curl -sS -G "${GRAPH}/${container}" \
      --data-urlencode "fields=status_code" \
      --data-urlencode "access_token=${META_ACCESS_TOKEN}")"
    check_response "Instagram container status" "$resp"
    status="$(jq -r '.status_code' <<<"$resp")"
    [[ "$status" == "FINISHED" ]] && break
    [[ "$status" == "ERROR" || "$status" == "EXPIRED" ]] && die "Instagram container status: $status"
    sleep 5
  done
  [[ "$status" == "FINISHED" ]] || die "Instagram container not ready (status: $status)"

  resp="$(curl -sS -X POST "${GRAPH}/${IG_USER_ID}/media_publish" \
    --data-urlencode "creation_id=${container}" \
    --data-urlencode "access_token=${META_ACCESS_TOKEN}")"
  check_response "Instagram publish" "$resp"
  echo "Instagram post published: media id $(jq -r '.id' <<<"$resp")"
}

post_facebook() {
  local url="$1" caption="$2" resp
  resp="$(curl -sS -X POST "${GRAPH}/${FB_PAGE_ID}/photos" \
    --data-urlencode "url=${url}" \
    --data-urlencode "message=${caption}" \
    --data-urlencode "published=true" \
    --data-urlencode "access_token=${META_ACCESS_TOKEN}")"
  check_response "Facebook photo post" "$resp"
  echo "Facebook post published: post id $(jq -r '.post_id // .id' <<<"$resp")"
}

for image in "$@"; do
  name="$(basename "$image")"
  url="${PAGES_BASE_URL%/}/images/${name}"

  caption_file="${image%.*}.txt"
  if [[ -f "$caption_file" ]]; then
    caption="$(cat "$caption_file")"
  else
    caption="${DEFAULT_CAPTION:-}"
  fi

  echo "== ${name} =="
  echo "URL: ${url}"
  echo "Caption: ${caption:-<none>}"

  if [[ "$DRY_RUN" == "true" ]]; then
    echo "DRY_RUN: skipping upload check and API calls."
    continue
  fi

  wait_for_url "$url"

  if [[ "$POST_TO_INSTAGRAM" != "false" ]]; then
    # Instagram's content publishing API accepts JPEG only.
    case "$(tr '[:upper:]' '[:lower:]' <<<"$name")" in
      *.jpg|*.jpeg) post_instagram "$url" "$caption" ;;
      *) die "Instagram requires JPEG; ${name} is not a .jpg/.jpeg file." ;;
    esac
  fi

  if [[ "$POST_TO_FACEBOOK" != "false" ]]; then
    post_facebook "$url" "$caption"
  fi
done
