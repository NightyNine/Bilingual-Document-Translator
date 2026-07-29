# Bilingual Document Translator for LM Studio Bionic

Use the project-local skill at:

```text
.bionic/skills/bilingual-document-translator/SKILL.md
```

When the user asks to translate a formatted DOCX or PDF:

1. Read that `SKILL.md` completely and follow its workflow.
2. Keep every source paragraph and insert its Chinese or English translation immediately afterward.
3. Preview the whole document and lock a professional glossary before translating.
4. Continue through analysis, translation, review, finalization, and validation without pausing for ordinary ambiguity.
5. Write every deliverable under `Output Files/<source-stem>/` unless the user names another output root.
6. Do not generate a PDF unless the user explicitly requests one.

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
