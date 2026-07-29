# Bilingual Document Translator

[English](#english) | [简体中文](#简体中文)

A portable Agent Skill for translating formatted documents between Chinese and English while keeping the source text, document structure, and visual formatting.

It reads the complete document first, builds and locks a terminology glossary, translates every eligible paragraph, inserts the translation immediately after the source paragraph, reviews the result, and produces structural QA reports.

> The source document is never overwritten. PDF export is disabled by default.

---

## English

### Features

- Automatically translates Chinese to English and English to Simplified Chinese.
- Produces a bilingual document: each translation appears immediately after its source paragraph.
- Preserves DOCX styles, headings, tables, images, headers, footers, footnotes, text boxes, section breaks, hyperlinks, and reading order.
- Reads the entire document before translation and creates a domain-specific terminology glossary.
- Locks terminology before translation to improve consistency across long documents.
- Runs a separate review pass for omissions, mistranslations, terminology drift, names, numbers, and units.
- Processes large documents in resumable batches without pausing for ordinary ambiguities.
- Groups all deliverables under an output folder named after the source file.
- Supports local, private translation through Ollama.
- Can be installed for Hermes, Codex, Claude Code, GitHub Copilot, Cursor, OpenCode, and standards-compatible Agent Skills hosts.

### How it works

```text
Full-document preview
        ↓
Terminology extraction and glossary lock
        ↓
Paragraph-level Chinese ↔ English translation
        ↓
Independent bilingual review
        ↓
Formatting-preserving DOCX insertion
        ↓
Structural and semantic QA
```

### Supported inputs

| Input | Support | Notes |
| --- | --- | --- |
| `.docx` | Recommended | Best format and structure preservation |
| `.pdf` | Supported | Converted into a reflowable bilingual DOCX |
| Scanned PDF | Best effort | Requires Tesseract OCR; typography and complex layouts may differ |
| Legacy `.doc` | Convert first | Save or convert it to `.docx` before running the skill |

The final deliverable is an editable bilingual `.docx`. A PDF is created only when `--pdf` is explicitly requested.

### Output structure

Given:

```text
Original Files/
└── test.docx
```

The skill writes:

```text
Output Files/
└── test/
    ├── test.bilingual.docx
    ├── test.glossary.csv
    ├── test.qa-report.md
    └── test.qa.json
```

### Requirements

- Python 3.10 or newer
- A compatible AI agent, or [Ollama](https://ollama.com/) for the unattended local runner
- LibreOffice for PDF conversion/export and reliable rendering
- Tesseract only when OCR is needed for scanned PDFs

Python packages are listed in [`scripts/requirements.txt`](scripts/requirements.txt).

### Installation

Clone the repository:

```bash
git clone https://github.com/NightyNine/Bilingual-Document-Translator.git
cd Bilingual-Document-Translator
```

Install the skill for one host:

```bash
python3 scripts/install_skill.py --agent hermes
```

Supported values:

```text
hermes, codex, claude, copilot, cursor, opencode, agents
```

Install for every supported host:

```bash
python3 scripts/install_skill.py --agent all
```

Install into a specific project instead of the user-level skill directory:

```bash
python3 scripts/install_skill.py \
  --agent hermes \
  --scope project \
  --project-dir "/absolute/path/to/project"
```

Update an existing installation:

```bash
python3 scripts/install_skill.py --agent hermes --force
```

Install the document-processing dependencies inside the installed skill:

```bash
python3 scripts/bootstrap.py
```

### Use with an agent

Attach or point the agent to a DOCX or PDF and ask:

```text
Use the bilingual-document-translator skill to translate this document.
Keep it bilingual, preserve the original formatting, do not stop between
batches, and write the result to Output Files.
```

The skill instructs the agent to:

1. Read every translatable unit.
2. Identify the domain and create a terminology glossary.
3. Translate every unit without requesting routine approvals.
4. Review every translation.
5. Insert each translation directly after its source paragraph.
6. Validate the finished document before delivery.

### Fast local Ollama mode

The unattended runner completes analysis, glossary creation, translation, review, finalization, and validation in one resumable command:

```bash
python3 scripts/bootstrap.py

./.venv/bin/python scripts/ollama_runner.py \
  "/absolute/path/to/input.docx" \
  --work-dir "/absolute/path/to/work/input" \
  --output-dir "/absolute/path/to/Output Files" \
  --model "qwen3.6:latest" \
  --batch-size 80 \
  --launch-server
```

Use any locally installed Ollama model that can reliably return structured JSON. If a model repeatedly omits IDs or returns malformed responses, reduce `--batch-size` to `40`.

The runner is checkpointed. Re-run the same command after an interruption to continue from the saved state instead of starting over.

Add `--pdf` only when a PDF copy is required:

```bash
./.venv/bin/python scripts/ollama_runner.py \
  "/absolute/path/to/input.docx" \
  --work-dir "/absolute/path/to/work/input" \
  --output-dir "/absolute/path/to/Output Files" \
  --model "qwen3.6:latest" \
  --pdf
```

### Translation behavior

- Chinese paragraphs are translated into English.
- English paragraphs are translated into Simplified Chinese.
- Mixed-language paragraphs follow their dominant language.
- Code, URLs, formulas, identifiers, names, dates, numbers, and units are preserved.
- Existing bilingual paragraph pairs are detected to avoid unnecessary duplication.
- Ordinary terminology ambiguity does not pause the run; the safest contextual choice is recorded in the glossary.
- The original visible text remains unchanged, and the source file itself is never modified.

### Validation

The pipeline checks:

- complete translation and review coverage;
- source order and immediate translation placement;
- missing or duplicated units;
- tables, media, sections, headers, footers, and relationships;
- names, numbers, units, terminology consistency, and unsupported additions;
- DOCX package integrity and optional PDF creation.

The result is accepted only when the generated QA record passes.

### Limitations

- DOCX provides the strongest formatting preservation. PDF input must be reconstructed into an editable document.
- OCR quality depends on scan resolution, language data, page orientation, and image quality.
- Text embedded inside raster images is reported but is not silently replaced in the image.
- Highly complex Word fields, floating objects, or proprietary fonts may require visual inspection in Microsoft Word.
- Translation quality depends on the selected model and the source document quality.

### Privacy

When the Ollama runner is used, document text is sent only to the configured local Ollama endpoint. When the skill is run by another hosted agent, that agent's model and data-handling policy apply.

The repository does not store source documents, generated deliverables, temporary work data, or credentials.

### Repository layout

```text
.
├── README.md
├── SKILL.md
├── agents/
│   └── openai.yaml
├── references/
│   └── translation-policy.md
├── scripts/
│   ├── bootstrap.py
│   ├── document_pipeline.py
│   ├── install_skill.py
│   ├── ollama_runner.py
│   └── requirements.txt
└── LICENSE
```

### License

Released under the [MIT License](LICENSE).

---

## 简体中文

### 项目简介

`Bilingual-Document-Translator` 是一个可供多种 AI Agent 安装的双语文档翻译 Skill。

它会先完整预览文档、判断内容领域并生成专业词汇表，然后逐段进行中英互译。译文会紧跟在对应原文之后，最后再执行独立复核和结构检查。

源文件不会被覆盖，默认也不会生成 PDF。

### 主要功能

- 自动判断翻译方向：中文译成英文，英文译成简体中文。
- 保留原文，并在每段原文后紧接对应译文。
- 尽量保留 DOCX 的标题、样式、表格、图片、页眉页脚、脚注、文本框、超链接、分节和阅读顺序。
- 翻译前通读全文，识别专业领域并生成术语表。
- 翻译前锁定术语，减少长文档中的术语不一致。
- 翻译完成后逐段复核遗漏、错译、否定关系、人名、数字、单位和专业术语。
- 支持断点续跑，处理中途停止后可以从已有进度继续。
- 整个翻译过程默认连续执行，不因普通术语歧义暂停。
- 每个源文件的成品、词汇表和检查报告都会放进同名输出文件夹。
- 支持通过 Ollama 在本机完成翻译。

### 支持的文件

| 文件类型 | 支持情况 | 说明 |
| --- | --- | --- |
| `.docx` | 推荐 | 格式和结构保留效果最好 |
| `.pdf` | 支持 | 会重建为可编辑的双语 DOCX |
| 扫描版 PDF | 尽力处理 | 需要 Tesseract OCR，复杂版式可能发生变化 |
| 旧版 `.doc` | 需先转换 | 请先另存或转换为 `.docx` |

### 安装

```bash
git clone https://github.com/NightyNine/Bilingual-Document-Translator.git
cd Bilingual-Document-Translator
```

只安装到 Hermes：

```bash
python3 scripts/install_skill.py --agent hermes
```

安装到全部支持的 Agent：

```bash
python3 scripts/install_skill.py --agent all
```

目前安装脚本支持：

```text
Hermes、Codex、Claude Code、GitHub Copilot、Cursor、OpenCode
以及兼容 Agent Skills 标准的目录
```

如果已经安装过，需要更新：

```bash
python3 scripts/install_skill.py --agent hermes --force
```

安装文档处理依赖：

```bash
python3 scripts/bootstrap.py
```

### 使用方式

把 DOCX 或 PDF 文件交给 Agent，然后告诉它：

```text
使用 bilingual-document-translator skill 翻译这个文件。
保留双语和原始格式，整个过程不要停，
把结果保存到 Output Files。
```

如果输入文件是 `test.docx`，输出结果为：

```text
Output Files/
└── test/
    ├── test.bilingual.docx
    ├── test.glossary.csv
    ├── test.qa-report.md
    └── test.qa.json
```

其中：

- `test.bilingual.docx`：可编辑的双语文档。
- `test.glossary.csv`：翻译前锁定的专业词汇表。
- `test.qa-report.md`：便于阅读的检查报告。
- `test.qa.json`：机器可读取的详细检查结果。

### Hermes + Ollama 一口气执行

```bash
python3 scripts/bootstrap.py

./.venv/bin/python scripts/ollama_runner.py \
  "/绝对路径/Original Files/test.docx" \
  --work-dir "/绝对路径/work/test" \
  --output-dir "/绝对路径/Output Files" \
  --model "qwen3.6:latest" \
  --batch-size 80 \
  --launch-server
```

本地没有 `qwen3.6:latest` 时，可以把 `--model` 改成其他已安装且能够稳定输出 JSON 的 Ollama 模型。

同一个命令可以重复运行。脚本会读取检查点并继续未完成的阶段，不会重复从头翻译。

默认只生成 DOCX；只有明确需要 PDF 时才添加：

```bash
--pdf
```

### 注意事项

- DOCX 的格式保留效果最好；PDF 转换成可编辑文档时无法保证像素级一致。
- 扫描版 PDF 的识别效果取决于清晰度、方向和 OCR 语言包。
- 图片内部的文字不会被自动覆盖替换。
- 特别复杂的浮动对象、Word 域或专有字体可能仍需在 Microsoft Word 中人工查看。
- 使用本地 Ollama 时，文本只会发送给配置的本地 Ollama 服务；使用云端 Agent 时，请以相应平台的数据政策为准。

### 开源协议

本项目采用 [MIT License](LICENSE)。
