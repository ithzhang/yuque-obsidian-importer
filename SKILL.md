---
name: yuque-obsidian-importer
description: Import Yuque/语雀 `.lakebook` knowledge base exports into an Obsidian vault. Use when Codex needs to inspect, convert, batch import, clean, or validate Yuque lakebook archives, including preserving Yuque TOC hierarchy, converting Lake HTML to Markdown, localizing CDN images into `_assets`, writing frontmatter, and checking Obsidian-ready output.
---

# Yuque Obsidian Importer

## Overview

Use this skill to convert one or more Yuque `.lakebook` files into Obsidian-ready Markdown folders. Prefer the bundled script for actual imports; use the workflow below for inspection, validation, and troubleshooting.

Bundled script:

```bash
python scripts/import_lakebook_to_obsidian.py <lakebook> <vault> --target-name <folder-name>
```

The script:

- Reads `.lakebook` as a POSIX tar archive.
- Parses `$meta.json`, including the JSON-encoded `meta` field and `book.tocYml`.
- Converts Yuque Lake HTML from each document JSON into Markdown with `lakedoc`.
- Preserves Yuque TOC order with numbered Obsidian folders/files.
- Writes frontmatter with `title`, `source_url`, `yuque_slug`, `yuque_id`, `created`, `updated`, and `imported_at`.
- Downloads remote images into `<target>/_assets/` and rewrites them to Obsidian embeds.
- Avoids generating empty same-name directories for leaf documents.

## Setup

Install dependencies if the script cannot import them:

```bash
python -m pip install --user lakedoc pyyaml
```

Use network escalation when downloading Yuque images from `cdn.nlark.com` fails in the sandbox.

## Single Import

1. Confirm the archive format:

```bash
file "/path/to/name.lakebook"
tar -tf "/path/to/name.lakebook" | head
```

Expected: POSIX tar archive with one root directory, `$meta.json`, and many document `.json` files.

2. Import into a vault folder:

```bash
python scripts/import_lakebook_to_obsidian.py \
  "/path/to/name.lakebook" \
  "/path/to/Obsidian Vault" \
  --target-name "name"
```

3. If re-running an import you created earlier, use `--replace`:

```bash
python scripts/import_lakebook_to_obsidian.py \
  "/path/to/name.lakebook" \
  "/path/to/Obsidian Vault" \
  --target-name "name" \
  --replace
```

Only use `--replace` when the target directory is known to be generated import output.

## Batch Import

For a directory of lakebooks:

```bash
for f in /path/to/yuque/*.lakebook; do
  name=$(basename "$f" .lakebook)
  python scripts/import_lakebook_to_obsidian.py "$f" "/path/to/Obsidian Vault" --target-name "$name"
done
```

Before batch importing, check whether target folders already exist in the vault. Do not overwrite user-authored folders without explicit permission.

## Validation

Run these checks after every import:

```bash
target="/path/to/Obsidian Vault/name"

find "$target" -type f -name '*.md' | wc -l
rg -n '^yuque_slug:' "$target" | wc -l
find "$target/_assets" -type f 2>/dev/null | wc -l
find "$target" -type d -empty -print
rg -n 'cdn\.nlark\.com|yuque-test-import' "$target"
```

Interpretation:

- Markdown count should equal Yuque document count plus one `_导入说明.md`.
- `yuque_slug` count should equal the Yuque document count.
- Empty directory count should be zero.
- Remote CDN search should return no matches if image localization succeeded.

Validate Obsidian image embeds:

```bash
python -c "import pathlib,re; root=pathlib.Path('/path/to/Obsidian Vault'); target=root/'name'; pat=re.compile(r'!\\[\\[([^\\]]+)\\]\\]'); links=[(p,m.group(1)) for p in target.rglob('*.md') for m in pat.finditer(p.read_text(encoding='utf-8',errors='ignore'))]; missing=[(str(p),x) for p,x in links if not (root/x).exists()]; print('embeds',len(links)); print('missing_embeds',len(missing)); [print(a,b) for a,b in missing[:10]]"
```

`missing_embeds` must be `0`.

## Troubleshooting

- If `unzip` fails, do not treat the file as broken. `.lakebook` is normally tar, not zip.
- If image downloads fail with DNS or host resolution errors, rerun with network permission. The Markdown conversion can still succeed, but CDN links may remain remote.
- If output has empty same-name directories, clean only empty directories:

```bash
find "$target" -type d -empty -delete
```

- If a document has no exported body, keep the generated placeholder. Some Yuque lakebooks contain metadata-only document entries.
- If counts disagree, compare source slugs to imported frontmatter before claiming data loss.

