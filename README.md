# Bilingual Document Translator

[English](#english) | [简体中文](#简体中文)

Current version: **1.1.0**

A portable Agent Skill for translating formatted Word, PDF, and Excel files between Chinese and English while keeping the source text, document structure, and visual formatting. Chinese-dominant sources also receive a separate translation-only English copy.

It reads the complete file first, builds and locks a terminology glossary, translates every eligible paragraph or spreadsheet cell, reviews the result, and produces structural QA reports. Excel translations remain in the source cell on a new line, exactly like Alt+Enter.

> The source document is never overwritten. PDF export is disabled by default.

---

## English

### Features

- Automatically translates Chinese to English and English to Simplified Chinese.
- Produces a bilingual document: each translation appears immediately after its source paragraph.
- Automatically adds a translation-only `.english` file for Chinese-dominant sources; Chinese text is replaced by reviewed English while existing English remains unchanged.
- Preserves DOCX styles, headings, tables, images, headers, footers, footnotes, text boxes, section breaks, hyperlinks, and reading order.
- Supports `.xlsx` and macro-enabled `.xlsm`; each translated cell becomes `source + line break + translation` in the same cell, never the neighboring cell.
- Preserves worksheet names and visibility, formulas, merged ranges, row heights, column widths, fonts, fills, borders, number formats, alignment, tables, charts, images, hyperlinks, validation rules, conditional formatting, and VBA package data.
- Reads the entire document before translation and creates a domain-specific terminology glossary.
- Locks terminology before translation to improve consistency across long documents.
- Runs a separate review pass for omissions, mistranslations, terminology drift, names, numbers, and units.
- Processes large documents in resumable batches without pausing for ordinary ambiguities.
- Groups all deliverables under an output folder named after the source file.
- Supports local, private translation through Ollama or LM Studio.
- Can be installed for Hermes, Codex, Claude Code, GitHub Copilot, Cursor, OpenCode, LM Studio Bionic Code Projects, and standards-compatible Agent Skills hosts.

### How it works

```text
Full-document preview
        ↓
Terminology extraction and glossary lock
        ↓
Paragraph/cell-level Chinese ↔ English translation
        ↓
Independent bilingual review
        ↓
Formatting-preserving Word or same-cell Excel insertion
        ↓
Conditional translation-only English copy
        ↓
Structural and semantic QA
```

### Supported inputs

| Input | Support | Notes |
| --- | --- | --- |
| `.docx` | Recommended | Best format and structure preservation |
| `.pdf` | Supported | Converted into a reflowable bilingual DOCX |
| Scanned PDF | Best effort | Requires Tesseract OCR; typography and complex layouts may differ |
| `.xlsx` | Supported | Translation is appended inside the original cell after a line break |
| `.xlsm` | Supported | Same-cell translation; embedded VBA package data is preserved |
| Legacy `.doc` | Convert first | Save or convert it to `.docx` before running the skill |
| Legacy `.xls` | Convert first | Save or convert it to `.xlsx` before running the skill |

The final deliverable matches the editable Office family of the input: `.docx` for DOCX/PDF, `.xlsx` for XLSX, and `.xlsm` for XLSM. Chinese-dominant sources additionally produce `.english.docx`, `.english.xlsx`, or `.english.xlsm`. A PDF is created only for DOCX/PDF input when `--pdf` is explicitly requested.

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
    ├── test.english.docx
    ├── test.glossary.csv
    ├── test.qa-report.md
    └── test.qa.json
```

For a Chinese-dominant `budget.xlsx`, the output folder contains both `budget.bilingual.xlsx` and `budget.english.xlsx`; the glossary and both QA files are stored in the same folder. English-dominant and genuinely mixed sources do not receive the extra English copy.

### Requirements

- Python 3.10 or newer
- A compatible AI agent, [Ollama](https://ollama.com/), or the [LM Studio local server](https://lmstudio.ai/docs/developer/core/server)
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
hermes, codex, claude, copilot, cursor, opencode, agents, bionic
```

Install for every supported host:

```bash
python3 scripts/install_skill.py --agent all
```

`--agent all` installs all hosts that have a documented user-level Skill directory. Bionic is installed separately at project scope because Bionic does not currently publish a global Skill directory.

Install into an LM Studio Bionic Code Project:

```bash
python3 scripts/install_skill.py \
  --agent bionic \
  --scope project \
  --project-dir "/absolute/path/to/bionic-code-project"
```

Open that directory as a Bionic Code Project, then ask Bionic:

```text
Read .bionic/bilingual-document-translator.md and use it to translate
Original Files/test.docx without pausing.
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

Attach or point the agent to a DOCX, PDF, XLSX, or XLSM file and ask:

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
5. Insert each Word translation after its source paragraph, or append each Excel translation inside the source cell after one line break.
6. Validate the finished document before delivery.

### Fast local Ollama or LM Studio mode

The unattended runner completes analysis, glossary creation, translation, review, finalization, and validation in one resumable command:

```bash
python3 scripts/bootstrap.py

./.venv/bin/python scripts/local_runner.py \
  "/absolute/path/to/input.docx" \
  --work-dir "/absolute/path/to/work/input" \
  --output-dir "/absolute/path/to/Output Files" \
  --provider ollama \
  --model "qwen3.6:latest" \
  --batch-size 80 \
  --launch-server
```

Use any locally installed Ollama model that can reliably return structured JSON. If a model repeatedly omits IDs or returns malformed responses, reduce `--batch-size` to `40`.

For LM Studio, start the local server from the Developer tab or with `lms server start`, then run:

```bash
./.venv/bin/python scripts/local_runner.py \
  "/absolute/path/to/input.docx" \
  --work-dir "/absolute/path/to/work/input" \
  --output-dir "/absolute/path/to/Output Files" \
  --provider lmstudio \
  --model "your-lm-studio-model-id" \
  --batch-size 80
```

The default LM Studio endpoint is `http://127.0.0.1:1234`. Use `--base-url` for another endpoint. If authentication is enabled, set `LM_API_TOKEN` or pass `--api-key`.

The runner is checkpointed. Re-run the same command after an interruption to continue from the saved state instead of starting over.

### Reliable offline Hermes mode

Telegram requires an internet connection, but the Hermes desktop client can translate fully offline through a locally installed Ollama or LM Studio model. The Skill includes a durable job manager so a five-minute agent tool timeout, closed chat turn, desktop reconnect, or Hermes Gateway restart does not terminate a long translation.

For normal Hermes use, the agent calls one deterministic entrypoint in a tracked background terminal. It starts or resumes the durable worker and waits for the completion notification without keeping the chat turn open:

```bash
./.venv/bin/python scripts/hermes_entry.py translate \
  "/absolute/path/to/input.docx" \
  --output-dir "/absolute/path/to/Output Files" \
  --provider ollama \
  --model "qwen3.6:latest"
```

The entrypoint also converts legacy `.doc` files with macOS `textutil` while preserving the original source. Use `hermes_entry.py status` with the same input and output root after reconnecting.

The lower-level durable job command remains available for recovery and diagnostics:

```bash
./.venv/bin/python scripts/background_job.py start \
  "/absolute/path/to/input.xlsx" \
  --work-dir "/private/tmp/input_bilingual_work" \
  --output-dir "/absolute/path/to/Output Files" \
  --provider ollama \
  --model "qwen3.6:latest" \
  --batch-size 80 \
  --launch-server
```

The command returns immediately. The detached worker writes its PID, command, timestamps, and state to `background-job.json`, streams the runner output to `background-job.log`, and continues using the normal translation checkpoints.

Check progress from any later Hermes session:

```bash
./.venv/bin/python scripts/background_job.py status \
  --work-dir "/private/tmp/input_bilingual_work"
```

Resume an interrupted job without starting over:

```bash
./.venv/bin/python scripts/background_job.py resume \
  --work-dir "/private/tmp/input_bilingual_work"
```

Hermes agents should launch `background_job.py wait --work-dir ...` through their tracked terminal with background execution and completion notification. They must not run `local_runner.py` or manual batch loops inside a five-minute `execute_code` call.

The same command accepts Excel input without any special flag:

```bash
./.venv/bin/python scripts/local_runner.py \
  "/absolute/path/to/budget.xlsx" \
  --work-dir "/absolute/path/to/work/budget" \
  --output-dir "/absolute/path/to/Output Files" \
  --provider lmstudio \
  --model "your-lm-studio-model-id"
```

Add `--pdf` only when a PDF copy is required:

```bash
./.venv/bin/python scripts/local_runner.py \
  "/absolute/path/to/input.docx" \
  --work-dir "/absolute/path/to/work/input" \
  --output-dir "/absolute/path/to/Output Files" \
  --provider ollama \
  --model "qwen3.6:latest" \
  --pdf
```

`--pdf` applies only to DOCX/PDF input. Excel input intentionally rejects it.

### Translation behavior

- Chinese paragraphs are translated into English.
- English paragraphs are translated into Simplified Chinese.
- Exception for Chinese-dominant Chinese→English jobs: a paragraph or cell already written in English is preserved exactly once in the bilingual output; it is not copied again and is not translated back into Chinese. English-dominant documents still receive normal English→Chinese translation.
- Mixed-language paragraphs follow their dominant language.
- Code, URLs, formulas, identifiers, names, dates, numbers, and units are preserved.
- Existing bilingual paragraph pairs are detected to avoid unnecessary duplication.
- Ordinary terminology ambiguity does not pause the run; the safest contextual choice is recorded in the glossary.
- The original visible text remains unchanged, and the source file itself is never modified.
- In Excel, formula, numeric/date, error, empty, chart, and image-text cells are not translated. Eligible text cells use one Alt+Enter-compatible line break inside the same cell and have wrap text enabled.

### Validation

The pipeline checks:

- complete translation and review coverage;
- source order and immediate translation placement;
- missing or duplicated units;
- tables, media, sections, headers, footers, and relationships;
- Excel same-cell placement, wrap-text styles, formulas, merges, sheet names, tables, charts, media, hyperlinks, validations, conditional formatting, and VBA package preservation;
- names, numbers, units, terminology consistency, and unsupported additions;
- DOCX package integrity and optional PDF creation.

The result is accepted only when the generated QA record passes.

### Limitations

- DOCX provides the strongest formatting preservation. PDF input must be reconstructed into an editable document.
- XLSX/XLSM text stored in worksheet cells is supported. Text embedded in charts, drawings, images, form controls, external data connections, or formula results is preserved but not translated.
- OCR quality depends on scan resolution, language data, page orientation, and image quality.
- Text embedded inside raster images is reported but is not silently replaced in the image.
- Highly complex Word fields, floating objects, or proprietary fonts may require visual inspection in Microsoft Word.
- Translation quality depends on the selected model and the source document quality.

### Privacy

When the local runner is used, document text is sent only to the configured Ollama or LM Studio endpoint. When the skill is run by another hosted agent, that agent's model and data-handling policy apply.

The repository does not store source documents, generated deliverables, temporary work data, or credentials.

### Repository layout

```text
.
├── README.md
├── SKILL.md
├── agents/
│   ├── bionic.md
│   └── openai.yaml
├── references/
│   └── translation-policy.md
├── scripts/
│   ├── bootstrap.py
│   ├── document_pipeline.py
│   ├── spreadsheet_pipeline.py
│   ├── install_skill.py
│   ├── local_runner.py
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

它会先完整预览文件、判断内容领域并生成专业词汇表，然后逐段或逐单元格进行中英互译。Word 译文紧跟原段落；Excel 译文通过 Alt+Enter 同等的换行写在原单元格内，最后再执行独立复核和结构检查。

如果原文件整体以中文为主，除了双语成品，还会自动生成一份纯英文 `.english` 文件：中文内容直接替换为复核后的英文译文，原本已经是英文的内容保持不变，文件结构和格式对象不重建。

源文件不会被覆盖，默认也不会生成 PDF。

### 主要功能

- 自动判断翻译方向：中文译成英文，英文译成简体中文。
- 保留原文，并在每段原文后紧接对应译文。
- 中文主导的源文件额外生成纯英文 `.english.docx`、`.english.xlsx` 或 `.english.xlsm`。
- 尽量保留 DOCX 的标题、样式、表格、图片、页眉页脚、脚注、文本框、超链接、分节和阅读顺序。
- 支持 `.xlsx` 和含宏的 `.xlsm`；Excel 中采用“原文 + 单元格内换行 + 译文”，不会把译文写到旁边或下一行的单元格。
- 保留工作表名称及隐藏状态、公式、合并单元格、行高、列宽、字体、填充、边框、数字格式、对齐、表格、图表、图片、超链接、数据验证、条件格式和 VBA 包内容。
- 翻译前通读全文，识别专业领域并生成术语表。
- 翻译前锁定术语，减少长文档中的术语不一致。
- 翻译完成后逐段复核遗漏、错译、否定关系、人名、数字、单位和专业术语。
- 支持断点续跑，处理中途停止后可以从已有进度继续。
- 整个翻译过程默认连续执行，不因普通术语歧义暂停。
- 每个源文件的成品、词汇表和检查报告都会放进同名输出文件夹。
- 支持通过 Ollama 或 LM Studio 在本机完成翻译。
- 支持安装到 LM Studio Bionic Code Project。

### 支持的文件

| 文件类型 | 支持情况 | 说明 |
| --- | --- | --- |
| `.docx` | 推荐 | 格式和结构保留效果最好 |
| `.pdf` | 支持 | 会重建为可编辑的双语 DOCX |
| 扫描版 PDF | 尽力处理 | 需要 Tesseract OCR，复杂版式可能发生变化 |
| `.xlsx` | 支持 | 译文在原单元格内换行追加 |
| `.xlsm` | 支持 | 同单元格翻译，并保留 VBA 包内容 |
| 旧版 `.doc` | 需先转换 | 请先另存或转换为 `.docx` |
| 旧版 `.xls` | 需先转换 | 请先另存或转换为 `.xlsx` |

### 安装

```bash
git clone https://github.com/NightyNine/Bilingual-Document-Translator.git
cd Bilingual-Document-Translator
```

只安装到 Hermes：

```bash
python3 scripts/install_skill.py --agent hermes
```

安装到具有全局 Skill 目录的全部 Agent：

```bash
python3 scripts/install_skill.py --agent all
```

目前安装脚本支持：

```text
Hermes、Codex、Claude Code、GitHub Copilot、Cursor、OpenCode、LM Studio Bionic
以及兼容 Agent Skills 标准的目录
```

Bionic 当前没有公开的全局 Skill 目录，因此需要安装到具体 Code Project：

```bash
python3 scripts/install_skill.py \
  --agent bionic \
  --scope project \
  --project-dir "/Bionic代码项目的绝对路径"
```

在 Bionic 中把该目录打开为 Code Project，然后输入：

```text
读取 .bionic/bilingual-document-translator.md，
使用它翻译 Original Files/test.docx，整个过程不要暂停。
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

把 DOCX、PDF、XLSX 或 XLSM 文件交给 Agent，然后告诉它：

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
    ├── test.english.docx
    ├── test.glossary.csv
    ├── test.qa-report.md
    └── test.qa.json
```

其中：

- `test.bilingual.docx`：可编辑的双语文档。
- `test.english.docx`：中文主导源文件对应的纯英文可编辑文档；英文主导或真正混合文档不生成该文件。
- `test.glossary.csv`：翻译前锁定的专业词汇表。
- `test.qa-report.md`：便于阅读的检查报告。
- `test.qa.json`：机器可读取的详细检查结果。

如果输入是 `budget.xlsx`，主文件会保存为
`Output Files/budget/budget.bilingual.xlsx`；如果工作簿以中文为主，还会生成
`Output Files/budget/budget.english.xlsx`。双语文件中每个需要翻译的文字单元格会变成：

```text
原文
译文
```

两行内容位于同一个单元格中，中间是一个 Excel 单元格内换行（相当于 Alt+Enter），不会占用相邻单元格。

### Ollama 或 LM Studio 一口气执行

```bash
python3 scripts/bootstrap.py

./.venv/bin/python scripts/local_runner.py \
  "/绝对路径/Original Files/test.docx" \
  --work-dir "/绝对路径/work/test" \
  --output-dir "/绝对路径/Output Files" \
  --provider ollama \
  --model "qwen3.6:latest" \
  --batch-size 80 \
  --launch-server
```

本地没有 `qwen3.6:latest` 时，可以把 `--model` 改成其他已安装且能够稳定输出 JSON 的 Ollama 模型。

使用 LM Studio 时，先在 Developer 页面启动本地服务器，或运行 `lms server start`：

```bash
./.venv/bin/python scripts/local_runner.py \
  "/绝对路径/Original Files/test.docx" \
  --work-dir "/绝对路径/work/test" \
  --output-dir "/绝对路径/Output Files" \
  --provider lmstudio \
  --model "LM Studio 中显示的模型 ID" \
  --batch-size 80
```

LM Studio 默认地址为 `http://127.0.0.1:1234`。如果服务器启用了认证，可以设置 `LM_API_TOKEN` 或传入 `--api-key`。

同一个命令可以重复运行。脚本会读取检查点并继续未完成的阶段，不会重复从头翻译。

翻译 Excel 时直接把输入路径换成 `.xlsx` 或 `.xlsm`，不需要额外参数：

```bash
./.venv/bin/python scripts/local_runner.py \
  "/绝对路径/Original Files/budget.xlsx" \
  --work-dir "/绝对路径/work/budget" \
  --output-dir "/绝对路径/Output Files" \
  --provider lmstudio \
  --model "LM Studio 中显示的模型 ID"
```

DOCX/PDF 输入默认只生成 DOCX；只有明确需要 PDF 时才添加：

```bash
--pdf
```

Excel 输入不生成 PDF，并且会拒绝 `--pdf`。

### 注意事项

- 中文主导的中译英任务中，如果某个段落或单元格本身已经是英文，双语版只原样保留这一份英文，不再追加相同英文，也不会把它反向翻译成中文。只有英文主导的英译中文档才正常执行英文→中文。
- DOCX 的格式保留效果最好；PDF 转换成可编辑文档时无法保证像素级一致。
- Excel 只翻译工作表单元格中的文字。公式、数值/日期、错误值、空单元格以及图表、绘图或图片内部文字会原样保留，不会被覆盖。
- 扫描版 PDF 的识别效果取决于清晰度、方向和 OCR 语言包。
- 图片内部的文字不会被自动覆盖替换。
- 特别复杂的浮动对象、Word 域或专有字体可能仍需在 Microsoft Word 中人工查看。
- 使用本地 Ollama 或 LM Studio 时，文本只会发送给配置的本地服务；使用云端 Agent 时，请以相应平台的数据政策为准。

### 开源协议

本项目采用 [MIT License](LICENSE)。
