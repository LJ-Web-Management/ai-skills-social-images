# ai-skills-social-images

Static asset host for daily AI-skill social images, served through GitHub Pages and
auto-published to Instagram and a Facebook Page. There is no website, blog, or page content here,
only image files.

## Repository structure

```
.github/
  workflows/
    deploy-pages.yml           # Deploys the repo to GitHub Pages (also called by the workflow below)
    publish-social-image.yml   # Deploy → verify image URL → publish to Instagram + Facebook
  state/
    published-images.json      # Duplicate-protection record (written by the workflow only)
images/
  .gitkeep
  ai-skills-YYYY-MM-DD-<slug>.jpg
scripts/
  publish_social.py            # Meta Graph API publishing + state handling
.nojekyll
README.md
```

## Image naming

- Images go in `images/` only, named `ai-skills-YYYY-MM-DD-<slug>.jpg`, e.g.
  `images/ai-skills-2026-10-08-give-ai-context-first.jpg`.
- The slug is lowercase letters, digits, and hyphens. Other names are rejected.
- **Never overwrite an earlier image.** Always add a new file. If a push modifies an existing
  image, the workflow fails and publishes nothing.
- **Use JPEG.** Instagram's publishing API does not accept PNG. A PNG is rejected before anything
  is posted, so both platforms stay in step.

## Public URL format

```
https://lj-web-management.github.io/ai-skills-social-images/images/FILENAME.jpg
```

## Caption

The caption comes from the filename slug. Nothing is added to or changed in the image:

| Filename | Caption |
| --- | --- |
| `ai-skills-2026-10-08-give-ai-context-first.jpg` | `AI skill: Give AI Context First.` |
| `ai-skills-2026-10-08.jpg` (no slug) | `AI skill for 2026-10-08.` |

`ai`, `api`, `gpt`, `llm`, `seo`, `ui`, `ux` are written in upper case.

## How publishing works

`publish-social-image.yml` runs when a `.jpg`/`.jpeg`/`.png` is pushed under `images/` on `main`,
or when run manually. It:

1. selects the newly added image(s) in the push;
2. deploys the repository to GitHub Pages (via `deploy-pages.yml`, Environment `github-pages`);
3. waits until the exact image URL returns HTTP 200 with `image/jpeg`/`image/png`, without
   authentication or redirects, and serves the same bytes as the committed file;
4. resolves a Facebook **Page** access token for `FACEBOOK_PAGE_ID` (before anything is posted,
   so a token problem stops the run before Instagram publishes);
5. creates an Instagram media container, polls it until `FINISHED`, publishes it once, then reads
   `GET /{media-id}?fields=permalink` and stores it as `instagram_permalink`;
6. posts the same image URL to the Facebook Page once, using the Page Photos endpoint (below);
7. records the result in `.github/state/published-images.json`.

Logs show only IDs, URLs, and statuses. Access tokens are never printed.

### Facebook publishing method

Facebook posts use the Graph API **Page Photos** endpoint with a **Page access token**:

```
POST https://graph.facebook.com/v23.0/{FACEBOOK_PAGE_ID}/photos
  url=<public GitHub Pages image URL>
  message=<caption>
  published=true
Authorization: Bearer <Page access token>
```

The response's `post_id` is stored as `facebook_post_id`. The `/feed` endpoint is not used, and
no deprecated permissions are used or needed.

If Facebook returns an `(#200)` error saying a permission "is not available" or "has been
deprecated", the photo was posted with a **User** token instead of a Page token. The workflow prevents this automatically.
It calls `GET /me`: if the secret is already the Page's token, it is used as-is. Otherwise it
calls `GET /{FACEBOOK_PAGE_ID}?fields=access_token` to get the Page token and uses that for
the post. If no Page token can be obtained, the run fails before anything is published.

If any step fails, the workflow run fails. A successful publish is never retried.

## GitHub Environment and secrets

The workflow uses the GitHub Environment named exactly **`github-pages`**. It needs these
**Environment secrets** (Settings → Environments → `github-pages` → Environment secrets):

| Secret | Value |
| --- | --- |
| `META_PAGE_ACCESS_TOKEN` | Long-lived Facebook **Page** access token for the Page linked to the Instagram account (a long-lived User token of a Page admin also works; the Page token is derived from it at run time) |
| `INSTAGRAM_USER_ID` | Instagram professional (Business/Creator) account ID |
| `FACEBOOK_PAGE_ID` | Facebook Page ID |

The workflow sends the token to Meta only in an `Authorization` header. It never prints it or
writes it to files, state, or commits.

**`GITHUB_TOKEN` is automatic.** GitHub creates it for every workflow run. Do **not** create a
`GITHUB_TOKEN` secret. The workflow uses it only to commit the state file.

Optional repository variable: `GRAPH_API_VERSION` (default `v23.0`).

Required token permissions:

| Permission | Used for |
| --- | --- |
| `pages_show_list` | Finding the Page and its Page token |
| `pages_read_engagement` | Reading the Page and its token |
| `pages_manage_posts` | `POST /{page-id}/photos` |
| `instagram_basic` | Reading the Instagram media permalink |
| `instagram_content_publish` | Instagram container and `media_publish` |
| `business_management` | Only if the Page is owned by a Business portfolio |

No other permissions are needed. Deprecated user-posting permissions are not used and must not be requested.

## Running the workflow manually

GitHub → **Actions** → **Publish social image** → **Run workflow** (branch `main`):

- **image_path:** the image to publish, e.g. `images/ai-skills-2026-10-08-give-ai-context-first.jpg`.
  Leave it blank to use the most recently added image.
- **dry_run:** tick to deploy, verify the public URL, and run read-only Meta checks: Page
  token lookup and Instagram permalink lookup. It never publishes and never writes state.

From a terminal:

```bash
gh workflow run publish-social-image.yml -R LJ-Web-Management/ai-skills-social-images -f image_path=images/ai-skills-2026-10-08-give-ai-context-first.jpg -f dry_run=true
```

A manual run of an image that is already published does nothing and succeeds. Use it to finish
a run that failed partway, such as Instagram posted but Facebook failed.

## Verifying the public image URL

```bash
curl -sI https://lj-web-management.github.io/ai-skills-social-images/images/FILENAME.jpg
```

Expect `HTTP/2 200` and `content-type: image/jpeg`, with no redirect. Opening the URL in a
private browser window should show the image without a login prompt.

## Duplicate protection

`.github/state/published-images.json` records each image's path, SHA-256 hash, commit SHA,
`instagram_media_id`, `instagram_permalink`, `facebook_post_id`, and timestamps.

- If Instagram succeeded but Facebook failed, a re-run publishes **only** to Facebook. A recorded
  `instagram_media_id` is never published again. If the permalink is missing, it is filled in
  with a read-only lookup.

- If an image (by path or identical content) is already recorded as published, the workflow
  exits successfully without posting.
- Before each platform's publish call, an `*_attempted_at` marker is committed and pushed.
  If the call then fails with an unclear result (e.g. network timeout), that platform is
  **not** retried automatically. The run fails with an "attempted … but its result was never
  recorded" error. Check the Instagram/Facebook account, then edit the state file by hand:
  add the real `instagram_media_id`/`facebook_post_id` if it did post, or delete the
  `*_attempted_at` line if it did not. Then run the workflow again.
- If Meta clearly rejects a request (HTTP 4xx), the marker is removed again, so a re-run can retry.
- State commits use `[skip ci]`. `.github/state/` is not a trigger path, and pushes made with
  `GITHUB_TOKEN` do not start new workflow runs.
- Runs are serialized (`concurrency: publish-social-image`). Push one new image per commit and
  wait for the run to finish before pushing the next. If a queued run is ever cancelled, publish
  that image with a manual run.

## Getting images into the repository

> **Warning:** the local Codex image generator still needs an authorized way to push the
> generated image into this repository, such as a logged-in `gh`/git credential helper on that
> machine, an SSH deploy key with write access, or a fine-grained GitHub token stored in the
> operating system's credential store. **Never** put tokens in the generator's prompt, memory
> file, source code, or image files, and never commit them to this repository.

After the push, the workflow handles deployment and publishing. The generator should only add
a new, uniquely named JPEG under `images/` and push it to `main`.

## Security

This repository is public. It must never contain access tokens, API keys, passwords, or other
secrets. Credentials live only in the `github-pages` Environment secrets.
