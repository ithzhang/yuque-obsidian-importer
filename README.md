# Yuque Obsidian Importer

[中文说明](README.zh-CN.md)

Codex skill and helper script for importing Yuque/语雀 `.lakebook` knowledge-base exports into an Obsidian vault.

It converts Yuque Lake HTML documents to Markdown, preserves the Yuque TOC hierarchy, downloads Yuque CDN images into local `_assets` folders, and writes Obsidian-friendly frontmatter.

## What It Does

- Reads `.lakebook` files as POSIX tar archives.
- Parses Yuque `$meta.json` and `book.tocYml`.
- Converts Lake HTML to Markdown with `lakedoc`.
- Creates numbered folders/files to preserve Yuque ordering.
- Writes frontmatter with Yuque source metadata.
- Localizes images into `<knowledge-base>/_assets/`.
- Validates empty directories, remote CDN leftovers, and missing Obsidian embeds.

## Requirements

```bash
python -m pip install --user lakedoc pyyaml
```

Optional but recommended:

```bash
brew install ripgrep
```

## Use As A Codex Skill

Install this repository as a Codex skill, then restart Codex so it can discover the skill.

Typical request:

```text
Use yuque-obsidian-importer to import /path/to/foo.lakebook into my Obsidian vault.
```

The skill lives in `SKILL.md`; the deterministic importer is in:

```text
scripts/import_lakebook_to_obsidian.py
```

## Direct Script Usage

Import one lakebook:

```bash
python scripts/import_lakebook_to_obsidian.py \
  "/path/to/知识库.lakebook" \
  "/path/to/Obsidian Vault"
```

By default, the target folder name is inferred from the `.lakebook` filename.

Specify a target folder:

```bash
python scripts/import_lakebook_to_obsidian.py \
  "/path/to/知识库.lakebook" \
  "/path/to/Obsidian Vault" \
  --target-name "知识库"
```

Re-run and replace a generated import folder:

```bash
python scripts/import_lakebook_to_obsidian.py \
  "/path/to/知识库.lakebook" \
  "/path/to/Obsidian Vault" \
  --target-name "知识库" \
  --replace
```

Only use `--replace` for directories known to be generated import output.

## Batch Import

```bash
for f in /path/to/yuque/*.lakebook; do
  name=$(basename "$f" .lakebook)
  python scripts/import_lakebook_to_obsidian.py "$f" "/path/to/Obsidian Vault" --target-name "$name"
done
```

Check for existing target folders before batch importing to avoid overwriting user-authored notes.

## Validation

After importing:

```bash
target="/path/to/Obsidian Vault/知识库"

find "$target" -type f -name '*.md' | wc -l
rg -n '^yuque_slug:' "$target" | wc -l
find "$target/_assets" -type f 2>/dev/null | wc -l
find "$target" -type d -empty -print
rg -n 'cdn\.nlark\.com|yuque-test-import' "$target"
```

Expected:

- Markdown count = Yuque document count + 1 `_导入说明.md`.
- `yuque_slug` count = Yuque document count.
- Empty directory count = `0`.
- No `cdn.nlark.com` matches if image localization succeeded.

Validate Obsidian embeds:

```bash
python -c "import pathlib,re; root=pathlib.Path('/path/to/Obsidian Vault'); target=root/'知识库'; pat=re.compile(r'!\\[\\[([^\\]]+)\\]\\]'); links=[(p,m.group(1)) for p in target.rglob('*.md') for m in pat.finditer(p.read_text(encoding='utf-8',errors='ignore'))]; missing=[(str(p),x) for p,x in links if not (root/x).exists()]; print('embeds',len(links)); print('missing_embeds',len(missing)); [print(a,b) for a,b in missing[:10]]"
```

`missing_embeds` should be `0`.

## Notes

- `.lakebook` is normally a tar archive, not a zip archive.
- If image downloads fail because of DNS/network restrictions, rerun in an environment with network access. Markdown conversion can still succeed, but remote image links may remain.
- Some Yuque exports contain metadata-only documents with no body. The script keeps a placeholder note for those entries.
