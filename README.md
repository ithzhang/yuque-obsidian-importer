# 语雀 Obsidian 导入器

<p align="right">
  <strong>中文</strong> |
  <a href="./README.en.md">English</a>
</p>

这是一个 Codex skill 和配套脚本，用来把语雀导出的 `.lakebook` 知识库导入到 Obsidian Vault。

它会把语雀 Lake HTML 文档转换成 Markdown，保留语雀目录层级，下载语雀 CDN 图片到本地 `_assets` 目录，并为每篇文档写入 Obsidian 友好的 frontmatter。

## 功能

- 将 `.lakebook` 作为 POSIX tar 归档读取。
- 解析语雀 `$meta.json` 和 `book.tocYml`。
- 使用 `lakedoc` 将 Lake HTML 转换为 Markdown。
- 用编号目录和文件名保留语雀目录顺序。
- 为每篇文档写入 `title`、`source_url`、`yuque_slug`、`yuque_id`、`created`、`updated`、`imported_at` 等 frontmatter。
- 将远程图片下载到 `<知识库>/_assets/`。
- 将图片链接改写为 Obsidian 本地嵌入引用。
- 校验空目录、远程 CDN 残留和缺失的 Obsidian 图片引用。

## 依赖

```bash
python -m pip install --user lakedoc pyyaml
```

可选但推荐安装：

```bash
brew install ripgrep
```

`ripgrep` 提供 `rg` 命令，用于导入后的快速校验。

## 作为 Codex Skill 使用

把这个仓库安装为 Codex skill 后，重启 Codex，让 Codex 重新发现 skill。

典型请求：

```text
使用 yuque-obsidian-importer 把 /path/to/foo.lakebook 导入到我的 Obsidian Vault。
```

skill 说明文件：

```text
SKILL.md
```

确定性导入脚本：

```text
scripts/import_lakebook_to_obsidian.py
```

## 直接运行脚本

导入单个 `.lakebook`：

```bash
python scripts/import_lakebook_to_obsidian.py \
  "/path/to/知识库.lakebook" \
  "/path/to/Obsidian Vault"
```

默认情况下，目标文件夹名称会从 `.lakebook` 文件名自动推导。

指定目标文件夹：

```bash
python scripts/import_lakebook_to_obsidian.py \
  "/path/to/知识库.lakebook" \
  "/path/to/Obsidian Vault" \
  --target-name "知识库"
```

重新导入并替换已有的生成目录：

```bash
python scripts/import_lakebook_to_obsidian.py \
  "/path/to/知识库.lakebook" \
  "/path/to/Obsidian Vault" \
  --target-name "知识库" \
  --replace
```

只有在确认目标目录是脚本生成的导入结果时，才使用 `--replace`。

## 批量导入

导入某个目录下的所有 `.lakebook`：

```bash
for f in /path/to/yuque/*.lakebook; do
  name=$(basename "$f" .lakebook)
  python scripts/import_lakebook_to_obsidian.py "$f" "/path/to/Obsidian Vault" --target-name "$name"
done
```

批量导入前，先检查 Obsidian Vault 中是否已经存在同名目标目录，避免覆盖手写笔记。

## 导入后校验

导入完成后运行：

```bash
target="/path/to/Obsidian Vault/知识库"

find "$target" -type f -name '*.md' | wc -l
rg -n '^yuque_slug:' "$target" | wc -l
find "$target/_assets" -type f 2>/dev/null | wc -l
find "$target" -type d -empty -print
rg -n 'cdn\.nlark\.com|yuque-test-import' "$target"
```

预期结果：

- Markdown 文件数 = 语雀文档数 + 1 个 `_导入说明.md`。
- `yuque_slug` 数量 = 语雀文档数。
- 空目录数量应为 `0`。
- 如果图片本地化成功，不应再出现 `cdn.nlark.com`。

校验 Obsidian 图片嵌入是否都能找到本地文件：

```bash
python -c "import pathlib,re; root=pathlib.Path('/path/to/Obsidian Vault'); target=root/'知识库'; pat=re.compile(r'!\\[\\[([^\\]]+)\\]\\]'); links=[(p,m.group(1)) for p in target.rglob('*.md') for m in pat.finditer(p.read_text(encoding='utf-8',errors='ignore'))]; missing=[(str(p),x) for p,x in links if not (root/x).exists()]; print('embeds',len(links)); print('missing_embeds',len(missing)); [print(a,b) for a,b in missing[:10]]"
```

`missing_embeds` 应为 `0`。

## 常见问题

### `.lakebook` 不能用 unzip 解压，是文件坏了吗？

不是。语雀 `.lakebook` 通常是 tar 归档，不是 zip 归档。用下面命令检查：

```bash
file "/path/to/知识库.lakebook"
tar -tf "/path/to/知识库.lakebook" | head
```

### 为什么会有 `_assets` 目录？

`_assets` 用来存放从语雀 CDN 下载下来的图片。Markdown 文件中使用 Obsidian wiki embed 引用这些图片：

```md
![[知识库/_assets/image.png]]
```

这样 Markdown 保持纯文本，图片也能离线访问。

### 图片下载失败怎么办？

如果遇到 DNS、网络或沙箱限制，Markdown 转换仍可成功，但图片可能保留为远程链接。请在有网络权限的环境下重新运行导入。

### 为什么有些文档正文为空？

部分语雀导出的 `.lakebook` 中会存在只有元数据、没有正文的文档条目。脚本会保留占位说明，避免目录和文档计数丢失。

### 可以清理空目录吗？

可以，只删除空目录：

```bash
find "$target" -type d -empty -delete
```

不要删除包含 `.md` 或 `_assets` 的目录。
