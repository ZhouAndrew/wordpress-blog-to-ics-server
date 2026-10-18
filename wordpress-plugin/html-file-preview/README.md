# HTML File Preview 0.2.2-beta.1 (WordPress)

Version 2 upgrades **the existing `html-file-preview` plugin** to add PDF-style settings that v1 was missing. This hotfix disables unsolicited previews. It enhances the native `core/file` Gutenberg block; it does not create a custom uploader, a new block type, or a shortcode. Existing HTML File blocks work without conversion.

## Features

- Native File upload/select/link and native download-button settings are retained.
- Local `.html` and `.htm` files may be previewed in the editor and published posts **only after Show inline embed is turned on for that block**.
- Select an HTML File block → sidebar **HTML preview** → **Show inline embed** (on/off) and **Height in pixels** (100–2000px, default 600px).
- The controls are stored per File block as `hfpShowPreview` and `hfpPreviewHeight` inside the Gutenberg comment. **These differ from the PDF-only attributes** `displayPreview` and `previewHeight`, because WordPress core may serialize `displayPreview` as an `application/pdf` object.
- For all existing and new HTML File blocks, preview defaults to **off**. No iframe will be injected without an explicit saved `hfpShowPreview: true`. This fixes involuntary previews from 0.2.1; no bulk migration is required.
- Only same-origin HTTP(S) `.html`/`.htm` URLs are previewed. A known HTML attachment ID resolves its direct media URL even if the link points to an attachment page.
- Preview iframes use `sandbox="allow-scripts"` **without** `allow-same-origin`; previews cannot access the parent document's cookies or DOM. No arbitrary remote HTML embeds.
- Core PDF, ICS and all other files retain their native functionality.

## Diagnose “no visible change”

After updating, open **WordPress Admin → Tools → HTML Preview Diagnostics**. Confirm the
installed plugin version is `0.2.2-beta.1`. You can enter a post/page ID to count
`core/file` HTML blocks versus `core/html` and Embed blocks.

The File block must be selected (not the surrounding paragraph or Custom HTML
block) and the **Block** tab must be open in the editor's right sidebar. The
HTML preview panel is only shown for same-site `.html`/`.htm` File blocks.

If the editor still does not show the panel, open browser Developer Tools → Console
while editing a post and inspect `window.hfpPreviewRuntime`:

- `undefined` means the editor script did not load.
- `{ loaded: true, settingsRegistered: true }` means the script and custom attribute schema loaded. Select the File block and open **Block** settings.
- `settingsRegistered: false` indicates a core File registration conflict; report this along with the WordPress version.

You may also run `wp --path=/var/www/html/wordpress plugin get html-file-preview --fields=name,status,version` on the server to verify the installed plugin version.

Version 0.2.1 improved fallback support for the File block's `textLinkHref`,
uses a numeric height input matching WordPress's File preview semantics, and
uses the actual asset modification time as part of editor script cache busting.

If no relevant File block is found, insert **File** and select your HTML
attachment. The plugin cannot turn a `Custom HTML` or `Embed` block into a File
block automatically.

## Update from 0.1.0-beta.1

1. WordPress → Plugins → Add New Plugin → Upload Plugin → choose `html-file-preview-0.2.2-beta.1.zip`.
2. Choose **Replace current with uploaded** if WordPress detects the existing v1 plugin. Keep the plugin activated.
3. Edit an existing HTML File block; open the block sidebar (gear icon) and expand **HTML preview**.
4. Change the preview toggle or height, save the post, and check the public article.

To install fresh: upload the same ZIP and activate HTML File Preview. Zip root is `html-file-preview/` and the main file is `html-file-preview/html-file-preview.php`.

### HTML upload permissions

WordPress intentionally restricts HTML uploads by default. This plugin does **not** bypass the platform's upload MIME restrictions or grant new permissions. Your existing trusted-admin upload configuration (such as `allow-admin-html-upload.php`) may be used to add HTML to Media Library. After selecting an existing HTML attachment, the plugin takes over its preview. Allow uploading HTML only for trusted administrators; uploads can contain JavaScript.

### Server response requirements

The media URL must send HTML as renderable `text/html`, not `Content-Disposition: attachment`; site CSP/X-Frame-Options must allow framing. JavaScript may run in the sandbox but its origin is opaque, so scripts requiring same-origin APIs/storage/cookies may not work. Do not add `allow-same-origin` alongside `allow-scripts` on same-site content.

## Tests

```sh
php -l html-file-preview.php
php tests/unit.php
node --check assets/editor.js
node tests/editor.test.cjs
```

These are local static and contract tests, **not an assertion that a live WordPress editor was tested**. The production editing flow should also be tested on the target WordPress install using an existing `.html` File block, fresh upload, toggle off/on, height changes, frontend inspection, and PDF regression.

## License

MIT — Copyright (c) 2026 ZhouAndrew. See `LICENSE`.

## 0.2.2 hotfix: no unsolicited previews

`0.2.1` inserted an iframe automatically whenever the saved File block was HTML,
including old posts that had **no visible on/off switch**. `0.2.2` changes the
default to **off** on both frontend and in-editor. This is a breaking default
chosen intentionally to prevent unsolicited iframes.

To turn on a preview for **one** HTML File block: select that File block; in
its **Block** sidebar expand **HTML preview** and enable **Show inline embed**.
Only that block will then get an iframe. Height remains per block. If the media
URL is not yet available, the toggle is still shown and a status hint appears.

If there is no HTML preview inspector at all, open Firefox developer tools and
read `window.hfpPreviewRuntime`: if undefined the editor script did not load.
The plugin's Tools → HTML Preview Diagnostics screen displays the loaded version
and asset URL. The server-side default-off safeguard still applies even if the
JavaScript enhancement fails.

Rollback: deactivate HTML File Preview to restore the original native File
markup. Deactivation never deletes or modifies saved posts.
