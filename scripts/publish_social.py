#!/usr/bin/env python3
"""Publish one image from images/ to Instagram and a Facebook Page, at most once per platform.

Usage: publish_social.py IMAGE_PATH [--dry-run]

Environment (secrets come from the github-pages GitHub Environment, never from files):
  META_PAGE_ACCESS_TOKEN  Facebook Page access token
  INSTAGRAM_USER_ID       Instagram professional account ID
  FACEBOOK_PAGE_ID        Facebook Page ID
  PAGES_BASE_URL          default https://lj-web-management.github.io/ai-skills-social-images
  GRAPH_API_VERSION       default v23.0
  GRAPH_BASE_URL          default https://graph.facebook.com (override only for local tests)
  URL_TIMEOUT_SECONDS     how long to wait for the image to go live (default 600)
  STATE_PUSH              "false" commits state locally without pushing (local tests only)

Duplicate protection: every publish attempt is committed to .github/state/published-images.json
and pushed BEFORE the Meta publish call is made. A platform with a recorded attempt but no
recorded ID is never retried automatically; it must be resolved by hand (see README).
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

STATE_FILE = ".github/state/published-images.json"
PATH_RE = re.compile(
    r"^images/ai-skills-(\d{4}-\d{2}-\d{2})(?:-([a-z0-9]+(?:-[a-z0-9]+)*))?\.(jpg|jpeg|png)$"
)
ACRONYMS = {"ai": "AI", "api": "API", "gpt": "GPT", "llm": "LLM", "llms": "LLMs", "seo": "SEO", "ui": "UI", "ux": "UX"}
CONTENT_TYPES = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}

TOKEN = os.environ.get("META_PAGE_ACCESS_TOKEN", "")
PAGES_BASE_URL = os.environ.get(
    "PAGES_BASE_URL", "https://lj-web-management.github.io/ai-skills-social-images"
).rstrip("/")
GRAPH = "{}/{}".format(
    os.environ.get("GRAPH_BASE_URL", "https://graph.facebook.com").rstrip("/"),
    os.environ.get("GRAPH_API_VERSION") or "v23.0",
)
URL_TIMEOUT = int(os.environ.get("URL_TIMEOUT_SECONDS") or 600)
STATE_PUSH = os.environ.get("STATE_PUSH", "true") != "false"


class Failure(Exception):
    pass


class MetaError(Failure):
    """definite=True means Meta rejected the request, so nothing was published."""

    def __init__(self, message, definite):
        super().__init__(message)
        self.definite = definite


def redact(text):
    text = str(text)
    return text.replace(TOKEN, "***") if TOKEN else text


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def caption_for(date, slug):
    if not slug:
        return f"AI skill for {date}."
    words = [ACRONYMS.get(w, w.capitalize()) for w in slug.split("-")]
    return f"AI skill: {' '.join(words)}."


# ---------- Meta Graph API ----------

def graph(method, path, params):
    url = f"{GRAPH}/{path}"
    data = None
    if method == "GET":
        url += "?" + urllib.parse.urlencode(params)
    else:
        data = urllib.parse.urlencode(params).encode()
    # Token goes in a header so it never appears in URLs, request bodies, or error text.
    req = urllib.request.Request(url, data=data, method=method, headers={"Authorization": f"Bearer {TOKEN}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        try:
            err = json.loads(body).get("error", {})
            msg = f"{err.get('message')} (code {err.get('code')}, subcode {err.get('error_subcode')})"
        except (ValueError, AttributeError):
            msg = body[:300]
        raise MetaError(f"HTTP {e.code}: {redact(msg)}", definite=400 <= e.code < 500)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        raise MetaError(f"request did not complete: {redact(e)}", definite=False)


def instagram_create_container(ig_user, image_url, caption):
    resp = graph("POST", f"{ig_user}/media", {"image_url": image_url, "caption": caption})
    container = resp.get("id")
    if not container:
        raise Failure("Instagram container response had no id.")
    print(f"Instagram container created: {container}")
    for _ in range(60):
        status = graph("GET", container, {"fields": "status_code"}).get("status_code")
        print(f"Instagram container status: {status}")
        if status == "FINISHED":
            return container
        if status in ("ERROR", "EXPIRED"):
            raise Failure(f"Instagram container ended with status {status}.")
        time.sleep(5)
    raise Failure("Instagram container did not reach FINISHED within 5 minutes.")


def instagram_publish(ig_user, container):
    media_id = graph("POST", f"{ig_user}/media_publish", {"creation_id": container}).get("id")
    if not media_id:
        raise MetaError("Instagram publish response had no media id.", definite=False)
    return media_id


def facebook_publish(page_id, image_url, caption):
    resp = graph("POST", f"{page_id}/photos", {"url": image_url, "message": caption, "published": "true"})
    post_id = resp.get("post_id") or resp.get("id")
    if not post_id:
        raise MetaError("Facebook response had no post id.", definite=False)
    return post_id


# ---------- Public URL check ----------

def wait_for_image(url, sha256, content_type):
    deadline = time.time() + URL_TIMEOUT
    last = "no response"
    while True:
        try:
            with urllib.request.urlopen(urllib.request.Request(url), timeout=30) as resp:
                ctype = resp.headers.get("Content-Type", "").split(";")[0].strip()
                body = resp.read()
                if resp.geturl() != url:
                    last = f"redirected to {resp.geturl()}"
                elif ctype != content_type:
                    last = f"content-type {ctype or 'missing'}"
                elif hashlib.sha256(body).hexdigest() != sha256:
                    last = "served file does not match the committed image yet"
                else:
                    print(f"Image is publicly reachable: {url} ({ctype}, {len(body)} bytes)")
                    return
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = str(e)
        if time.time() >= deadline:
            raise Failure(f"Image URL not publicly reachable after {URL_TIMEOUT}s: {url} ({last})")
        print(f"Waiting for {url}: {last}")
        time.sleep(10)


# ---------- State ----------

def git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout.strip()


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"images": []}
    with open(STATE_FILE) as f:
        return json.load(f)


def save_state(state, message):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)
        f.write("\n")
    try:
        git("add", STATE_FILE)
        git("commit", "-q", "-m", f"{message} [skip ci]")
        if not STATE_PUSH:
            return
        for attempt in range(3):
            try:
                git("pull", "-q", "--rebase", "origin", "main")
                git("push", "-q", "origin", "HEAD:main")
                return
            except subprocess.CalledProcessError:
                if attempt == 2:
                    raise
                time.sleep(5)
    except subprocess.CalledProcessError as e:
        raise Failure(f"Could not save publish state ({message}): {redact(e.stderr or e)}")


# ---------- Main ----------

def publish(path, dry_run):
    m = PATH_RE.match(path)
    if not m:
        raise Failure(
            f"{path} is not a valid image name. Expected images/ai-skills-YYYY-MM-DD[-slug].jpg|jpeg|png "
            "with a lowercase slug of letters, digits and hyphens."
        )
    date, slug, ext = m.groups()
    if not os.path.isfile(path):
        raise Failure(f"{path} does not exist on main.")
    with open(path, "rb") as f:
        sha256 = hashlib.sha256(f.read()).hexdigest()
    image_url = f"{PAGES_BASE_URL}/{path}"
    caption = caption_for(date, slug)
    print(f"Image:   {path}\nSHA-256: {sha256}\nURL:     {image_url}\nCaption: {caption}")

    state = load_state()
    entry = next((e for e in state["images"] if e["path"] == path), None)
    same_content = next((e for e in state["images"] if e["sha256"] == sha256 and e["path"] != path), None)

    if entry and entry["sha256"] != sha256:
        raise Failure(f"{path} changed after it was recorded. Images must never be overwritten; add a new file.")
    if same_content and not entry:
        print(f"Identical image already recorded as {same_content['path']}; not publishing again.")
        return
    if entry and entry.get("instagram_media_id") and entry.get("facebook_post_id"):
        print(f"Already published (Instagram {entry['instagram_media_id']}, "
              f"Facebook {entry['facebook_post_id']}); nothing to do.")
        return
    for platform, label, id_key in (("instagram", "Instagram", "instagram_media_id"),
                                    ("facebook", "Facebook", "facebook_post_id")):
        if entry and entry.get(f"{platform}_attempted_at") and not entry.get(id_key):
            raise Failure(
                f"The {label} publish of {path} was attempted at {entry[f'{platform}_attempted_at']} "
                "but its result was never recorded. Check the account manually, then update "
                f"{STATE_FILE} (see README) before re-running. Not retrying, to avoid a duplicate post."
            )

    need_ig = not (entry and entry.get("instagram_media_id"))
    need_fb = not (entry and entry.get("facebook_post_id"))
    if need_ig and ext == "png":
        raise Failure("Instagram publishing only accepts JPEG. Save the image as .jpg; nothing was published.")

    wait_for_image(image_url, sha256, CONTENT_TYPES[ext])

    if dry_run:
        print(f"DRY RUN: would publish to {'Instagram ' if need_ig else ''}{'Facebook' if need_fb else ''}. "
              "No Meta requests made, no state written.")
        return

    missing = [n for n in ("META_PAGE_ACCESS_TOKEN", "INSTAGRAM_USER_ID", "FACEBOOK_PAGE_ID") if not os.environ.get(n)]
    if missing:
        raise Failure(f"Missing github-pages Environment secret(s): {', '.join(missing)}")
    ig_user, page_id = os.environ["INSTAGRAM_USER_ID"], os.environ["FACEBOOK_PAGE_ID"]

    if not entry:
        entry = {"path": path, "sha256": sha256,
                 "commit": git("log", "-1", "--diff-filter=A", "--format=%H", "--", path),
                 "image_url": image_url, "caption": caption}
        state["images"].append(entry)

    if need_ig:
        container = instagram_create_container(ig_user, image_url, caption)
        entry["instagram_attempted_at"] = now()
        save_state(state, f"Start Instagram publish of {path}")
        try:
            media_id = instagram_publish(ig_user, container)
        except MetaError as e:
            if e.definite:
                del entry["instagram_attempted_at"]
                save_state(state, f"Clear rejected Instagram publish of {path}")
            raise Failure(f"Instagram publish failed: {e}")
        entry["instagram_media_id"] = media_id
        entry["instagram_published_at"] = now()
        print(f"Instagram published: media id {media_id}")

    if need_fb:
        entry["facebook_attempted_at"] = now()
        save_state(state, f"Start Facebook publish of {path}")
        try:
            post_id = facebook_publish(page_id, image_url, caption)
        except MetaError as e:
            if e.definite:
                del entry["facebook_attempted_at"]
                save_state(state, f"Clear rejected Facebook publish of {path}")
            raise Failure(f"Facebook publish failed: {e}")
        entry["facebook_post_id"] = post_id
        entry["facebook_published_at"] = now()
        print(f"Facebook published: post id {post_id}")

    entry["published_at"] = now()
    save_state(state, f"Record published {path}")
    print(f"Done: {path} published to Instagram and Facebook.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("image_path")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        publish(args.image_path, args.dry_run)
    except Failure as e:
        print(f"::error::{redact(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
