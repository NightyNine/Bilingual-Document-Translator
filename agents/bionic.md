# Bilingual Document Translator for LM Studio Bionic

Use the project-local skill at:

```text
.bionic/skills/bilingual-document-translator/SKILL.md
```

When the user asks to translate a formatted DOCX, PDF, XLSX, or XLSM:

1. Read that `SKILL.md` completely and follow its workflow.
2. For DOCX/PDF, keep every source paragraph and insert its Chinese or English translation immediately afterward.
3. For XLSX/XLSM, append the translation inside the source cell after one Alt+Enter-compatible line break. Never write it into an adjacent cell, and never replace formulas.
4. When the source is Chinese-dominant, also create the additional translation-only `.english.docx`, `.english.xlsx`, or `.english.xlsm` output. Preserve existing English text and all original formatting/objects.
5. In that Chinese→English job, keep source paragraphs or cells that are already English exactly once in the bilingual output. Do not append a duplicate English copy and do not translate them back into Chinese.
6. Preview the whole file and lock a professional glossary before translating.
7. Continue through analysis, translation, review, finalization, and validation without pausing for ordinary ambiguity.
8. Write every deliverable under `Output Files/<source-stem>/` unless the user names another output root.
9. Do not generate a PDF unless the user explicitly requests one for DOCX/PDF input. Excel input does not support PDF export.

For unattended local inference through LM Studio, start the local server in the Developer tab or run `lms server start`, then use:

```bash
python3 .bionic/skills/bilingual-document-translator/scripts/bootstrap.py

.bionic/skills/bilingual-document-translator/.venv/bin/python \
  .bionic/skills/bilingual-document-translator/scripts/local_runner.py \
  "/absolute/path/to/input.docx" \
  --work-dir "/absolute/path/to/work/input" \
  --output-dir "/absolute/path/to/Output Files" \
  --provider lmstudio \
  --model "your-lm-studio-model-id"
```

If LM Studio server authentication is enabled, set `LM_API_TOKEN` or pass `--api-key`.
