# HTML File Preview v0.1.0-beta.1 (WordPress Gutenberg)

MIT-licensed beta release of a WordPress plugin that **enhances the built-in File (`core/file`) block** rather than registering a competing uploader or modifying WordPress core.

## What changes

When the File block links to a **same-origin `.html` or `.htm` file**, the plugin adds an inline HTML iframe preview in the block editor and on the public post. The original filename link, download button, and other File-block behaviors remain unchanged. Existing File blocks are supported; no migration or shortcode is required. Other file types (including PDF and ICS) are unaffected.

Previews use an iframe with `sandbox="allow-scripts"` **without** `allow-same-origin`. Scripts inside a preview, if any, cannot access the parent page's DOM or site cookies. Site CSP, iframe headers, or download-disposition headers can still prevent a specific HTML file from rendering. The plugin does **not** loosen WordPress's HTML upload restrictions or change server MIME configuration.

## Install

1. Zip the `html-file-preview/` directory so the ZIP has `html-file-preview/html-file-preview.php` at its top level.
2. WordPress admin → Plugins → Add New Plugin → Upload Plugin → select the ZIP → Install Now → Activate.
3. Edit a post. Insert the native **File** block and select an HTML attachment already uploaded to the Media Library (or use a same-site HTML file URL). An inline preview appears automatically below the usual download link.
4. Existing posts containing HTML File blocks gain the preview after activation; disable the plugin to restore native appearance.

If your server sends `.html` with `Content-Disposition: attachment`, the browser will download rather than render it. Adjust the server's response for trusted files, not this plugin's security policy.

## Tests

Run from this directory:

```sh
php -l html-file-preview.php
php tests/unit.php
node tests/editor.test.cjs
```

An additional GitHub Actions job runs a real WordPress installation, activates the plugin and verifies `do_blocks()` for HTML and non-HTML File blocks, and builds a downloadable ZIP artifact.

## License

MIT — Copyright (c) 2026 ZhouAndrew. See `LICENSE`.
