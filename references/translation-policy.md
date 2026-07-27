# Translation Policy and Response Schemas

The current Hermes model performs semantic work; `document_pipeline.py` performs deterministic file work. Keep responses machine-readable and do not include prose outside the JSON object.

## Analysis response

```json
{
  "terms": [
    {
      "source": "chief resident",
      "target": "总住院医师",
      "direction": "en-to-zh",
      "domain": "medicine",
      "definition": "senior resident physician",
      "context_unit_ids": ["word/document.xml:12"],
      "confidence": "high",
      "notes": "Use consistently throughout the document."
    }
  ]
}
```

Analyze every supplied unit. Include recurring names, titles, abbreviations, measurements, legal/medical/technical phrases, and terms whose literal translation would be misleading. Do not add generic everyday words unless their domain sense differs.

## Translation response

```json
{
  "items": [
    {
      "id": "word/document.xml:12",
      "source_hash": "sha256-from-batch",
      "target": "译文"
    }
  ]
}
```

Return exactly the IDs in the batch. Preserve numbers, dates, units, citations, names, product codes, and formula syntax. Translate paragraph-level meaning and register rather than concatenating sentence fragments.

## Review response

```json
{
  "items": [
    {"id": "word/document.xml:12", "status": "ok"},
    {"id": "word/document.xml:13", "status": "replace", "target": "修订后的译文", "issues": ["terminology"]}
  ]
}
```

Review for omission, wrong direction, inverted negation, names, numbers, unit conversion, glossary drift, unsupported additions, and severe awkwardness. Leave a good translation as `ok`; do not stylistically rewrite it.

## Direction and exceptions

- Chinese text is translated to English; English text is translated to Chinese.
- Mixed paragraphs follow their dominant language, while code, URLs, formulas, identifiers, and standalone numbers remain unchanged.
- Existing bilingual pairs should be recognized from adjacent matching-language paragraphs and not duplicated.
- For ambiguous terminology, choose the best contextual term, record the alternative in glossary notes, and continue.
