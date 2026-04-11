# wp_log_parser

A configurable local CLI tool that fetches daily WordPress logs, parses Gutenberg `post_content`, and exports ICS events.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install requests pytest
```

## Dependency checks

Run dependency and environment validation:

```bash
python -m wp_log_parser validate-config --config ./config.json
```

## Configuration wizard

Run the interactive wizard:

```bash
python -m wp_log_parser init-config --wizard --config ./config.json
```

Sample wizard session:

```text
Welcome to wp_log_parser setup wizard

1) Fetch mode
Choose how to fetch posts.
  1) wpcli
  2) rest
[default: 1]
> 2

2) WordPress base URL
Example: https://example.com [default: ]
> https://blog.local

Username
WordPress username for REST API. [default: ]
> andrew

Application password
WordPress application password. [default: ]
> ********

8) Environment validation
[OK] module:json: Module available
[ERROR] rest: REST endpoint unreachable (401)

Configuration summary:
  - wordpress_mode: rest
  - app_password: an********rd

Save config
Write config to ./config.json? [default: y]
> y
```

## wp-cli mode
Use local WordPress installation + wp-cli command:

```bash
python -m wp_log_parser fetch-post --config ./config.json --post-id 123
```

## REST API mode
Use WordPress REST API with username + application password.

```bash
python -m wp_log_parser run-today --config ./config.json
```

## Troubleshooting

- `wp-cli not found`: set `wp_cli_path` correctly.
- `Path exists but does not look like WordPress`: set `wp_path` to WP root.
- `REST authentication failed`: verify username and application password.
- Validation failures do not mutate config files; run the setup wizard to change settings.

## Example commands

```bash
python -m wp_log_parser init-config --wizard
python -m wp_log_parser validate-config --config ./config.json
python -m wp_log_parser fetch-post --config ./config.json --post-id 10213
python -m wp_log_parser parse-post --config ./config.json --post-id 10213
python -m wp_log_parser run-today --config ./config.json
```

## Config file reference

See `example.config.json` for all supported fields.
