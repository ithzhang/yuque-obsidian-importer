#!/usr/bin/env python3
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import lakedoc
import yaml


INVALID_CHARS = r'[:/\\?*"<>\|]'
IMAGE_RE = re.compile(r'!\[[^\]]*\]\((https?://[^)]+)\)')


def clean_name(value: str, fallback: str = "无标题") -> str:
    value = (value or "").strip() or fallback
    value = re.sub(INVALID_CHARS, " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    value = value.rstrip(". ")
    return value[:120] or fallback


def unique_path(path: Path, used: set[Path]) -> Path:
    candidate = path
    index = 2
    while candidate in used or candidate.exists():
        candidate = path.with_name(f"{path.stem}-{index}{path.suffix}")
        index += 1
    used.add(candidate)
    return candidate


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def extract_lakebook(lakebook: Path, workdir: Path) -> Path:
    with tarfile.open(lakebook, "r") as archive:
        archive.extractall(workdir)
    roots = [p for p in workdir.iterdir() if p.is_dir()]
    if not roots:
        raise RuntimeError("lakebook archive did not contain a root directory")
    return roots[0]


def parse_meta(root: Path) -> dict:
    meta_file = root / "$meta.json"
    raw = read_json(meta_file)
    meta = raw.get("meta")
    if isinstance(meta, str):
        meta = json.loads(meta)
    if not isinstance(meta, dict):
        raise RuntimeError("$meta.json has an unsupported meta format")
    return meta


def load_docs(root: Path) -> dict[str, dict]:
    docs: dict[str, dict] = {}
    for path in root.glob("*.json"):
        if path.name == "$meta.json":
            continue
        raw = read_json(path)
        doc = raw.get("doc") or {}
        slug = doc.get("slug") or path.stem
        docs[slug] = doc
    return docs


def toc_entries(meta: dict) -> list[dict]:
    toc_yml = (meta.get("book") or {}).get("tocYml") or ""
    entries = yaml.safe_load(toc_yml) or []
    return [entry for entry in entries if isinstance(entry, dict)]


def convert_body(doc: dict) -> str:
    html = doc.get("body") or ""
    if not html.strip():
        description = doc.get("description") or doc.get("custom_description") or ""
        return description.strip()
    if "<!doctype html>" in html[:80].lower():
        html = re.sub(r"(?i)^<!doctype html>", "<!doctype lake>", html, count=1)
    elif "<!doctype lake>" not in html[:100].lower():
        html = "<!doctype lake>" + html
    return lakedoc.convert(
        html,
        default_title=False,
        table_infer_header=True,
        wrap=False,
    ).strip()


def yaml_quote(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def frontmatter(doc: dict, source_base: str, import_time: str) -> str:
    slug = doc.get("slug") or ""
    source_url = f"{source_base.rstrip('/')}/{slug}" if source_base and slug else ""
    fields = {
        "title": doc.get("title") or "无标题",
        "source": "yuque_lakebook",
        "source_url": source_url,
        "yuque_slug": slug,
        "yuque_id": doc.get("id"),
        "created": doc.get("created_at"),
        "updated": doc.get("updated_at") or doc.get("content_updated_at"),
        "imported_at": import_time,
    }
    lines = ["---"]
    for key, value in fields.items():
        if value is None or value == "":
            continue
        lines.append(f"{key}: {yaml_quote(value)}")
    lines.append("---")
    return "\n".join(lines)


def safe_asset_name(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    name = Path(parsed.path).name
    suffix = Path(name).suffix or ".bin"
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    stem = clean_name(Path(name).stem, "asset")[:80]
    return f"{stem}-{digest}{suffix}"


def download_asset(url: str, assets_dir: Path, cache: dict[str, str]) -> str | None:
    if url in cache:
        return cache[url]
    filename = safe_asset_name(url)
    target = assets_dir / filename
    if not target.exists():
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Codex lakebook importer)"},
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                data = response.read()
            assets_dir.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        except (urllib.error.URLError, TimeoutError, OSError):
            cache[url] = ""
            return None
    cache[url] = filename
    return filename


def localize_images(markdown: str, assets_dir: Path, asset_prefix: str, cache: dict[str, str]) -> str:
    def replace(match: re.Match) -> str:
        url = match.group(1)
        filename = download_asset(url, assets_dir, cache)
        if not filename:
            return match.group(0)
        return f"![[{asset_prefix}/{filename}]]"

    return IMAGE_RE.sub(replace, markdown)


def build_paths(entries: list[dict], docs: dict[str, dict], target_root: Path) -> tuple[dict[str, Path], dict[str, Path]]:
    folder_for_uuid: dict[str, Path] = {"": target_root}
    file_for_slug: dict[str, Path] = {}
    used: set[Path] = set()
    counters: dict[Path, int] = {}
    uuids_with_children = {
        str(entry.get("parent_uuid") or "")
        for entry in entries
        if str(entry.get("parent_uuid") or "")
    }

    def next_prefix(folder: Path) -> str:
        counters[folder] = counters.get(folder, 0) + 1
        return f"{counters[folder]:03d}"

    for entry in entries:
        entry_type = entry.get("type")
        uuid = str(entry.get("uuid") or "")
        parent_uuid = str(entry.get("parent_uuid") or "")
        parent_folder = folder_for_uuid.get(parent_uuid, target_root)
        title = clean_name(str(entry.get("title") or "无标题"))
        prefix = next_prefix(parent_folder)

        if entry_type == "TITLE" and uuid in uuids_with_children:
            folder = unique_path(parent_folder / f"{prefix} {title}", used)
            folder_for_uuid[uuid] = folder
        elif entry_type == "DOC":
            slug = str(entry.get("url") or "")
            doc = docs.get(slug) or {}
            doc_title = clean_name(str(doc.get("title") or title or slug), slug or "无标题")
            file_path = unique_path(parent_folder / f"{prefix} {doc_title}.md", used)
            file_for_slug[slug] = file_path
            if uuid in uuids_with_children:
                folder_for_uuid[uuid] = file_path.with_suffix("")

    for slug, doc in docs.items():
        if slug in file_for_slug:
            continue
        title = clean_name(str(doc.get("title") or slug), slug)
        prefix = next_prefix(target_root)
        file_for_slug[slug] = unique_path(target_root / f"{prefix} {title}.md", used)

    return file_for_slug, folder_for_uuid


def write_readme(target_root: Path, meta: dict, counts: dict[str, int], import_time: str) -> None:
    book = meta.get("book") or {}
    lines = [
        "# 语雀导入说明",
        "",
        f"- 导入时间：{import_time}",
        f"- 来源：{book.get('path') or ''}",
        f"- 文档数：{counts['docs']}",
        f"- 空正文文档数：{counts['empty']}",
        f"- 图片下载成功数：{counts['assets']}",
        "",
        "说明：本目录由 `.lakebook` 自动转换生成，正文由语雀 Lake HTML 转 Markdown。",
    ]
    (target_root / "_导入说明.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def import_lakebook(lakebook: Path, vault: Path, target_name: str, replace: bool) -> dict[str, int]:
    target_root = vault / target_name
    if target_root.exists():
        if not replace:
            raise RuntimeError(f"target directory already exists: {target_root}")
        shutil.rmtree(target_root)
    target_root.mkdir(parents=True)

    with tempfile.TemporaryDirectory(prefix="lakebook-", dir="/private/tmp") as tmp:
        root = extract_lakebook(lakebook, Path(tmp))
        meta = parse_meta(root)
        docs = load_docs(root)
        entries = toc_entries(meta)
        file_for_slug, folder_for_uuid = build_paths(entries, docs, target_root)

        for folder in sorted(set(folder_for_uuid.values()), key=lambda p: len(p.parts)):
            folder.mkdir(parents=True, exist_ok=True)

        import_time = dt.datetime.now().astimezone().isoformat(timespec="seconds")
        source_base = (meta.get("book") or {}).get("path") or ""
        assets_dir = target_root / "_assets"
        asset_cache: dict[str, str] = {}
        empty_count = 0

        for slug, doc in docs.items():
            output_path = file_for_slug[slug]
            output_path.parent.mkdir(parents=True, exist_ok=True)
            body = convert_body(doc)
            if not body.strip():
                empty_count += 1
                body = "> 此文档在 lakebook 中没有导出正文。"
            body = localize_images(body, assets_dir, f"{target_name}/_assets", asset_cache)
            text = f"{frontmatter(doc, source_base, import_time)}\n\n{body.strip()}\n"
            output_path.write_text(text, encoding="utf-8")

        counts = {
            "docs": len(docs),
            "empty": empty_count,
            "assets": sum(1 for filename in set(asset_cache.values()) if filename),
        }
        write_readme(target_root, meta, counts, import_time)
        return counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("lakebook", type=Path)
    parser.add_argument("vault", type=Path)
    parser.add_argument("--target-name")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()

    counts = import_lakebook(
        lakebook=args.lakebook.expanduser().resolve(),
        vault=args.vault.expanduser().resolve(),
        target_name=args.target_name or args.lakebook.expanduser().stem,
        replace=args.replace,
    )
    print(json.dumps(counts, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
