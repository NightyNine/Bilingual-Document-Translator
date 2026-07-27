---
name: bilingual-document-translator
description: Use when translating formatted DOCX or PDF files into reviewed bilingual documents while preserving structure, styles, tables, images, and reading order. Automatically preview the full document, build a terminology glossary, translate Chinese↔English paragraph by paragraph, validate the output, and continue without pausing for normal ambiguity.
license: MIT
metadata:
  hermes:
    tags: [translation, bilingual, DOCX, PDF, glossary, OCR, formatting]
    related_skills: [docx, pdf, ocr-and-documents]
---

# Bilingual Document Translator

## Overview

Translate a DOCX or PDF into a bilingual document using the current Hermes model. The source is never overwritten: every eligible paragraph remains intact and its translation is inserted immediately afterward using the source paragraph's visual formatting.

The workflow is checkpointed and model-agnostic. The bundled script handles extraction, stable IDs, JSON batch validation, OOXML insertion, PDF export, and structural QA; Hermes handles domain reading, terminology decisions, translation, and semantic review.

## When to Use

Use this skill when the user supplies a `.docx` or `.pdf` and requests Chinese↔English translation, bilingual output, professional terminology consistency, or preservation of document formatting. It supports text PDFs and OCR/reflow of scanned PDFs with explicit risk reporting.

Do not overwrite the source, silently skip eligible text, or stop for ordinary terminology ambiguity. Stop only for an unreadable/protected input or missing required runtime dependency, and report the exact remedy.

## Required Output

Unless the user explicitly requests another destination, create a task work directory and deliver:

- `<stem>.bilingual.docx` — editable bilingual document.
- `<stem>.bilingual.pdf` — exported PDF when LibreOffice is available.
- `<stem>.glossary.csv` — locked terminology table.
- `<stem>.qa-report.md` and `<stem>.qa.json` — structural and semantic review results.

Never include the user's source documents, temporary work directories, or API credentials in a skill repository.

## Workflow

Set absolute paths for the input, work directory, and output directory. Run the helper with the interpreter that has the dependencies listed in `scripts/requirements.txt`:

```bash
PIPE="${HERMES_SKILL_DIR}/scripts/document_pipeline.py"
python3 "$PIPE" prepare \
  "/absolute/input/document.docx" \
  --work-dir "/absolute/work/document"
```

If the runtime check reports missing Python packages, run the one-time bootstrap before starting the task:

```bash
python3 "${HERMES_SKILL_DIR}/scripts/bootstrap.py"
```

### 1. Prepare and read the complete document

`prepare` copies the source, extracts paragraphs from the main body, tables, headers, footers, comments, footnotes, endnotes, and text boxes, and records a stable source hash for every non-empty unit. For PDFs it creates a reflowable intermediate DOCX; scanned pages use OCR and are marked in the manifest.

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

Preserve names, numbers, dates, units, formulas, URLs, code, citations, and the source register. Translate the whole paragraph as a coherent unit, not sentence fragments. Continue fetching and ingesting batches until complete; do not ask the user to approve normal choices.

### 4. Review every translation

After all translations are stored, run a separate review pass:

```bash
python3 "$PIPE" next-batch --work-dir "/absolute/work/document" --phase review
```

Return one item per supplied ID with `status: "ok"` or `status: "replace"` and a corrected `target`. Correct omissions, inverted meaning, inconsistent glossary usage, names, numbers, and clearly unnatural phrasing. Do not rewrite an acceptable translation merely for style. Ingest every review batch before finalization.

### 5. Render and validate

```bash
python3 "$PIPE" finalize \
  --work-dir "/absolute/work/document" \
  --output-dir "/absolute/output/document"
```

The renderer clones each original paragraph and inserts its translation after it. It removes list numbering from the translated companion paragraph so bullets are not duplicated, while retaining paragraph indentation, heading styles, direct formatting, tables, images, sections, and relationships. It exports PDF through LibreOffice when available.

Accept the result only when `qa.json` passes. Also render the output PDF to page images and visually inspect all pages for overflow, broken tables, missing images, font tofu, OCR errors, and translated text that is not immediately after its source. For long documents, inspect a complete thumbnail montage plus every flagged/dense page.

```bash
python3 "$PIPE" validate --work-dir "/absolute/work/document"
```

## Translation and Formatting Rules

- Determine direction per content unit: Chinese→English, English→Chinese; preserve mixed technical tokens and non-linguistic units.
- Keep source text byte-for-byte in the source copy and visible textually unchanged in the output.
- Put the translation in a new paragraph directly after the source paragraph. Keep it in the same table cell, header/footer, footnote, or text box when possible.
- Reuse the source paragraph properties and predominant run formatting. Do not change source fonts or document-wide styles.
- Preserve images, tables, hyperlinks, fields, page setup, section breaks, and relationships. Text inside raster images is reported rather than silently altered.
- For scanned PDFs, preserve page order and basic flow; treat recovered typography, tables, and coordinates as best effort and report OCR confidence/layout risks.
- Keep the glossary authoritative across all batches. If a term has multiple valid translations, choose the contextually safest one and record the alternative in `notes`.

See [references/translation-policy.md](references/translation-policy.md) for compact response schemas and the review checklist.

## Common Pitfalls

1. **Translating before the glossary is complete:** `next-batch --phase translation` intentionally refuses to run until `lock-glossary` succeeds.
2. **Returning extra or missing IDs:** `ingest` requires an exact ID set and source hashes; regenerate only the failed batch.
3. **Duplicating list bullets:** the renderer removes `w:numPr` from the companion paragraph while retaining indentation.
4. **Losing layout by rebuilding from plain text:** always use the bundled OOXML renderer for DOCX; do not round-trip through Markdown.
5. **Treating OCR as ground truth:** inspect the flagged pages and record uncertain words or layout in QA.
6. **Overwriting the source:** output paths must be separate from the input; the script copies the source into the task work directory first.

## Verification Checklist

- [ ] Every non-empty translatable unit was analyzed before the glossary was locked.
- [ ] Glossary entries are deduplicated and exported as UTF-8 CSV.
- [ ] Every translatable ID has exactly one translation and one review result.
- [ ] Original text and order are present in the output, with the translation immediately following.
- [ ] Media, tables, sections, headers, footers, and relationships were not lost.
- [ ] Numbers, names, units, formulas, URLs, and glossary terms were checked.
- [ ] DOCX opens, PDF export succeeds or the report explains why it was skipped, and rendered pages were inspected.
- [ ] Source files and credentials are absent from the deliverable repository.
