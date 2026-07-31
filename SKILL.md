---
name: bilingual-document-translator
description: Use when translating formatted DOCX, PDF, XLSX, or XLSM files into reviewed bilingual documents while preserving structure and formatting. Automatically preview the full file, build a terminology glossary, translate Chinese↔English by content unit, keep Excel source and translation in the same cell separated by a line break, place deliverables in a source-named output folder, validate the result, and continue without pausing for normal ambiguity.
---

# Bilingual Document Translator

## Overview

Translate a DOCX, PDF, XLSX, or XLSM file using the current agent model. The source is never overwritten. In Word output, each eligible paragraph remains intact and its translation is inserted immediately afterward. In Excel output, the translation is appended inside the original cell as `original + line break + translation`, equivalent to entering a line break with Alt+Enter.

The workflow is checkpointed and model-agnostic. The bundled script handles extraction, stable IDs, JSON batch validation, OOXML insertion, optional PDF export, and structural QA; the host agent handles domain reading, terminology decisions, translation, and semantic review.

Do not overwrite the source, silently skip eligible text, or stop for ordinary terminology ambiguity. Stop only for an unreadable/protected input or missing required runtime dependency, and report the exact remedy.

## Required Output

Treat the requested output directory as an output root. Create one child directory named after the source filename without its extension. For example, translate `test.docx` into `Output Files/test/`.

Deliver:

- `<output-root>/<stem>/<stem>.bilingual.docx` — editable bilingual output for DOCX/PDF input.
- `<output-root>/<stem>/<stem>.bilingual.xlsx` or `.bilingual.xlsm` — editable bilingual workbook for Excel input.
- `<output-root>/<stem>/<stem>.glossary.csv` — locked terminology table.
- `<output-root>/<stem>/<stem>.qa-report.md` and `<output-root>/<stem>/<stem>.qa.json` — structural and semantic review results.

Do not create a PDF unless the user explicitly requests one. Never place generated files directly in the shared output root, and never include source documents, temporary work directories, or API credentials in a skill repository.

## Installation and Portability

This repository is one portable Agent Skills bundle. Its project name is `Bilingual-Document-Translator`; its standards-compliant skill ID and installed directory name are `bilingual-document-translator`.

Install it into one or more supported user-level skill directories:

```bash
python3 scripts/install_skill.py --agent all
```

Use `--agent hermes`, `codex`, `claude`, `copilot`, `cursor`, `opencode`, or `agents` for one host. LM Studio Bionic currently has no documented global Skill directory, so install it into a Bionic Code Project with `--agent bionic --scope project --project-dir "/absolute/project"`. Existing installations are never overwritten unless `--force` is supplied. Run `scripts/bootstrap.py` once inside an installed copy only when its document-processing dependencies are missing.

## Workflow

Resolve `SKILL_DIR` to the absolute directory containing this `SKILL.md`. Set absolute paths for the input, work directory, and output directory. Run the helper with the interpreter that has the dependencies listed in `scripts/requirements.txt`:

```bash
SKILL_DIR="/absolute/path/to/bilingual-document-translator"
PIPE="${SKILL_DIR}/scripts/document_pipeline.py"
python3 "$PIPE" prepare \
  "/absolute/input/document.docx" \
  --work-dir "/absolute/work/document"
```

If the runtime check reports missing Python packages, run the one-time bootstrap before starting the task:

```bash
python3 "${SKILL_DIR}/scripts/bootstrap.py"
```

For a fully unattended task using Ollama or LM Studio, prefer the resumable local runner. It performs every analysis, translation, review, finalize, and validate loop without asking the user between phases:

```bash
"${SKILL_DIR}/.venv/bin/python" \
  "${SKILL_DIR}/scripts/local_runner.py" \
  "/absolute/input/document.docx" \
  --work-dir "/absolute/work/document" \
  --output-dir "/absolute/output" \
  --provider ollama \
  --model "qwen3.6:latest" \
  --batch-size 80 \
  --launch-server
```

For LM Studio, start its local server and use `--provider lmstudio --model "<model-id>"`; the default endpoint is `http://127.0.0.1:1234`. If server authentication is enabled, set `LM_API_TOKEN` or pass `--api-key`. This fast local mode analyzes, translates, and reviews about 80 units per model call. Add `--pdf` only for DOCX/PDF input and only when the user asks for a PDF; Excel input rejects `--pdf`. Reduce `--batch-size` to 40 only if the local model repeatedly omits IDs or returns malformed JSON.

Use the manual phases below when the host agent model is not available through Ollama or LM Studio, or when an operator needs to inspect intermediate batches.

### 1. Prepare and read the complete document

`prepare` copies the source and records a stable source hash for every non-empty unit. For DOCX it extracts paragraphs from the main body, tables, headers, footers, comments, footnotes, endnotes, and text boxes. For PDF it creates a reflowable intermediate DOCX; scanned pages use OCR and are marked in the manifest. For XLSX/XLSM it extracts text cells from every worksheet, including hidden sheets, while excluding formulas, numeric/date cells, errors, and drawing text.

Read every analysis batch. Do not infer the domain from the first page only:

```bash
python3 "$PIPE" next-batch --work-dir "/absolute/work/document" --phase analysis
```

Return JSON with `terms`, where each term has at least `source`, `target`, and optionally `direction`, `domain`, `definition`, `context_unit_ids`, `confidence`, and `notes`. Save the response and ingest it:

```bash
python3 "$PIPE" ingest --work-dir "/absolute/work/document" \
  --phase analysis --response "/absolute/work/document/analysis-response.json"
```

Repeat until `next-batch` returns `"complete": true`. The analysis phase must cover every translatable unit before continuing.

### 2. Lock the glossary before translating

Consolidate duplicate terms and resolve inconsistent candidates using the whole-document context. Write a JSON array (or `{"terms": [...]}`) to `glossary.json`, then lock it:

```bash
python3 "$PIPE" lock-glossary \
  --work-dir "/absolute/work/document" \
  --file "/absolute/work/document/glossary.json"
```

This produces a UTF-8 CSV and unlocks the translation phase. Never translate before this command succeeds.

### 3. Translate all batches without pausing

Fetch translation batches only after the glossary is locked:

```bash
python3 "$PIPE" next-batch --work-dir "/absolute/work/document" --phase translation
```

Return exactly one item for every supplied ID:

```json
{
  "items": [
    {"id": "word/document.xml:4", "source_hash": "...", "target": "..."}
  ]
}
```

Preserve names, numbers, dates, units, formulas, URLs, code, citations, and the source register. Translate each whole paragraph or cell as a coherent unit, not sentence fragments. Continue fetching and ingesting batches until complete; do not ask the user to approve normal choices.

### 4. Review every translation

After all translations are stored, run a separate review pass:

```bash
python3 "$PIPE" next-batch --work-dir "/absolute/work/document" --phase review
```

Return one item per supplied ID with `status: "ok"` or `status: "replace"` and a corrected `target`. Correct omissions, inverted meaning, inconsistent glossary usage, names, numbers, and clearly unnatural phrasing. Do not rewrite an acceptable translation merely for style. Ingest every review batch before finalization.

### 5. Finalize and validate

```bash
python3 "$PIPE" finalize \
  --work-dir "/absolute/work/document" \
  --output-dir "/absolute/Output Files"
```

The finalizer automatically creates `/absolute/Output Files/<stem>/`. For DOCX/PDF, it clones each original paragraph and inserts its translation after it, suppressing duplicate list numbering while retaining indentation, styles, tables, images, sections, and relationships. For XLSX/XLSM, it appends `\n<translation>` inside the same source cell, enables wrap text only on translated cells, and leaves formulas and neighboring cells untouched.

Accept the result only when `qa.json` passes. In the default fast path, use OOXML structure, source-order, translation-placement, language, number, and terminology checks without producing a PDF. For Excel, also verify exact same-cell placement, wrap-text styles, formulas, merges, sheet names, charts, media, validations, conditional formatting, hyperlinks, and VBA-package preservation. If the user requests visual QA or a PDF for DOCX/PDF, finalize with `--pdf`, render page images, and inspect all pages for overflow, broken tables, missing images, font tofu, OCR errors, and misplaced translations.

```bash
python3 "$PIPE" finalize \
  --work-dir "/absolute/work/document" \
  --output-dir "/absolute/Output Files" \
  --pdf
```

```bash
python3 "$PIPE" validate --work-dir "/absolute/work/document"
```

## Translation and Formatting Rules

- Determine direction per content unit: Chinese→English, English→Chinese; preserve mixed technical tokens and non-linguistic units.
- Keep source text byte-for-byte in the source copy and visible textually unchanged in the output.
- For DOCX/PDF output, put the translation in a new paragraph directly after the source paragraph. Keep it in the same table cell, header/footer, footnote, or text box when possible.
- For XLSX/XLSM output, write `source\ntranslation` in the original cell. The separator must be one in-cell line break (Alt+Enter-compatible), never an adjacent row or column. Turn on wrap text for that cell.
- Never translate or replace formulas, numeric/date values, errors, empty cells, or text embedded in charts/images. Preserve sheet names, hidden states, merged ranges, row heights, column widths, fonts, fills, borders, number formats, alignment, formulas, hyperlinks, tables, charts, images, data validation, conditional formatting, and VBA content.
- Reuse the source paragraph properties and predominant run formatting. Do not change document-wide styles. Map an unavailable Chinese font alias only to its installed platform equivalent when necessary to keep text visible.
- Preserve images, tables, hyperlinks, fields, page setup, section breaks, and relationships. Text inside raster images is reported rather than silently altered.
- For scanned PDFs, preserve page order and basic flow; treat recovered typography, tables, and coordinates as best effort and report OCR confidence/layout risks.
- Keep the glossary authoritative across all batches. If a term has multiple valid translations, choose the contextually safest one and record the alternative in `notes`.

See [references/translation-policy.md](references/translation-policy.md) for compact response schemas and the review checklist.

## Common Pitfalls

1. **Translating before the glossary is complete:** `next-batch --phase translation` intentionally refuses to run until `lock-glossary` succeeds.
2. **Returning extra or missing IDs:** `ingest` requires an exact ID set and source hashes; regenerate only the failed batch.
3. **Duplicating list bullets:** the renderer explicitly suppresses inherited numbering on the companion paragraph while retaining indentation and heading formatting.
4. **Losing layout by rebuilding from plain text:** always use the bundled OOXML renderer; do not round-trip Office files through Markdown or CSV.
5. **Treating OCR as ground truth:** inspect the flagged pages and record uncertain words or layout in QA.
6. **Overwriting the source:** output paths must be separate from the input; the script copies the source into the task work directory first.
7. **Mixing files from different sources:** pass the shared output root to `finalize`; it creates the source-named child directory automatically.
8. **Writing an Excel translation to the next cell:** the required layout is `original + "\n" + translation` inside the same cell, with wrap text enabled.
9. **Assuming Bionic has a global Skill folder:** use the project-scope installer and ask Bionic to read `.bionic/bilingual-document-translator.md`; do not invent a user-level path.

## Verification Checklist

- [ ] Every non-empty translatable unit was analyzed before the glossary was locked.
- [ ] Glossary entries are deduplicated and exported as UTF-8 CSV.
- [ ] Every translatable ID has exactly one translation and one review result.
- [ ] Original text and order are present in the output, with the translation immediately following; Excel translations use the same cell and one line break.
- [ ] Media, tables, sections, headers, footers, and relationships were not lost.
- [ ] Numbers, names, units, formulas, URLs, and glossary terms were checked.
- [ ] DOCX or Excel output opens and structural checks pass; formulas and workbook objects are unchanged; PDF export and page inspection were performed only when requested for DOCX/PDF.
- [ ] Every generated deliverable is inside `<output-root>/<source-stem>/`.
- [ ] Source files and credentials are absent from the deliverable repository.
