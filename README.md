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

## Security

Do not commit Instagram or Facebook access tokens, API keys, passwords, or any other secrets
to this repository. It is public. Keep credentials in the automation's own secret store.

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
