# ai-skills-social-images

Static asset host for standalone social-media images, served through GitHub Pages.
This repository contains no website, blog, or pages — only image files.

## Public image URLs

Every image in `images/` is publicly available at:

```
https://GITHUB-USERNAME.github.io/ai-skills-social-images/images/FILENAME.jpg
```

Example:

```
https://GITHUB-USERNAME.github.io/ai-skills-social-images/images/ai-skills-2026-10-08.jpg
```

## File naming

- Store images only in `images/`.
- Use a unique, dated filename for every image: `ai-skills-YYYY-MM-DD.jpg` (or `.png`).
- Never overwrite an existing file. If more than one image is needed on the same day,
  add a suffix: `ai-skills-2026-10-08-2.jpg`.
- Use lowercase letters, digits, and hyphens only — no spaces.

## Deployment

`.github/workflows/deploy-pages.yml` deploys the repository contents to GitHub Pages on
every push to `main`. `.nojekyll` disables Jekyll processing so files are served as-is.

## Auto-posting to Instagram and Facebook

After every successful Pages deploy triggered by a push, the `post-social` job in the workflow:

1. finds images **newly added** under `images/` in that push (modified or re-deployed files are never reposted);
2. waits until each image's public URL returns the real image;
3. posts it to Instagram (container → wait for `FINISHED` → publish) and to the Facebook Page.

**Captions:** put the caption in a text file with the same name as the image, e.g.
`images/ai-skills-2026-10-08.txt` next to `images/ai-skills-2026-10-08.jpg`. Commit both in the
same push. If there is no `.txt` file, the `DEFAULT_CAPTION` variable is used.

**Instagram only accepts JPEG.** A `.png` will still post to Facebook, but the Instagram step fails.

### Where the IDs and tokens go

Never in this repository. Store them as **GitHub Actions secrets**:
**Settings → Secrets and variables → Actions → Secrets → New repository secret**.

| Secret | What it is |
| --- | --- |
| `META_ACCESS_TOKEN` | Long-lived **Page** access token for the Facebook Page linked to the Instagram account |
| `IG_USER_ID` | Instagram professional account ID (numeric) |
| `FB_PAGE_ID` | Facebook Page ID (numeric) |

Or from a terminal (prompts for the value so it is not saved in shell history):

```bash
gh secret set META_ACCESS_TOKEN -R GITHUB-USERNAME/ai-skills-social-images
```

Optional **variables** (same screen, **Variables** tab, not secret):

| Variable | Default | Purpose |
| --- | --- | --- |
| `DEFAULT_CAPTION` | empty | Caption when no `.txt` file exists |
| `GRAPH_API_VERSION` | `v23.0` | Meta Graph API version |
| `POST_TO_INSTAGRAM` | `true` | Set `false` to skip Instagram |
| `POST_TO_FACEBOOK` | `true` | Set `false` to skip Facebook |

### Getting the IDs and token

1. The Instagram account must be a **Business or Creator** account linked to a Facebook Page.
2. Create an app at <https://developers.facebook.com/apps> (type: Business) and add the
   **Instagram Graph API** / Facebook Login products.
3. In the [Graph API Explorer](https://developers.facebook.com/tools/explorer/), generate a User token with:
   `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`, `instagram_basic`,
   `instagram_content_publish` (and `business_management` if the Page is in a Business portfolio).
4. Exchange it for a long-lived user token, then call `GET /me/accounts` with it. The
   `access_token` returned for your Page is a long-lived Page token (no expiry) → `META_ACCESS_TOKEN`.
   The Page's `id` → `FB_PAGE_ID`.
5. Call `GET /{FB_PAGE_ID}?fields=instagram_business_account`; the returned `id` → `IG_USER_ID`.
6. For posting from your own accounts the app can stay in Development mode as long as you
   hold a role on the app; otherwise the permissions need App Review.

## Security

Do not commit Instagram or Facebook access tokens, API keys, passwords, or any other secrets
to this repository. It is public. Credentials live only in GitHub Actions secrets, which are
encrypted, masked in logs, and not readable by people viewing the repository.

## Validation checklist

Run these checks after setup and whenever something looks wrong.

1. **Repository is public**

   ```bash
   gh repo view GITHUB-USERNAME/ai-skills-social-images --json visibility -q .visibility
   ```

   Expected output: `PUBLIC`

2. **GitHub Pages URL opens without authentication** — open it in a private/incognito
   browser window, or:

   ```bash
   curl -sI https://GITHUB-USERNAME.github.io/ai-skills-social-images/images/.gitkeep
   ```

   Expected: `HTTP/2 200` with no login redirect.

3. **Image URL returns the actual image file**

   ```bash
   curl -sI https://GITHUB-USERNAME.github.io/ai-skills-social-images/images/FILENAME.jpg
   ```

   Expected: `HTTP/2 200` and `content-type: image/jpeg` (or `image/png`) — not `text/html`.

4. **Each daily image uses a new filename** — confirm no existing file was modified:

   ```bash
   git log --diff-filter=M --name-only --format= -- images/
   ```

   Expected: no output (images are only ever added, never modified).
