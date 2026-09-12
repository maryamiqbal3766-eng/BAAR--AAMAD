# Curated authoritative sources

This folder is BAAR-AAMAD's entire regulatory knowledge base. Nothing outside
it may be used to state a requirement.

## The rule this folder exists to enforce

> No authoritative evidence = no confident regulatory claim.

Every `Requirement` the system shows an exporter must trace back to a `chunk`
in one of these files, and every chunk carries the URL it came from. A
requirement with no chunk behind it is forced to REQUIRES VERIFICATION by
`core.rules.enforce_evidence_rule`, in code, where no model can talk past it.

## What a source file looks like

One JSON file per source. See `schema.md` for the full field list.

```jsonc
{
  "source_id":   "unique-slug",
  "source_name": "How the source should be cited on screen",
  "source_url":  "https://…",          // must resolve to the real document
  "publisher":   "European Union",
  "retrieved_at": "2026-09-12",
  "applies_to":  { "products": ["leather bags"], "destinations": ["Germany"] },

  "chunks": [                           // the evidence itself
    { "chunk_id": "slug#1", "locator": "Article 15(1)", "text": "…" }
  ],

  "requirements": [                     // interpretation of those chunks
    { "requirement_id": "REQ-…", "evidence_chunks": ["slug#1"], … }
  ]
}
```

`chunks[].text` is quoted from the cited source. Keep quotes short and
precise, and always set `locator` so a reader can find the passage. Never
write a sentence into `text` that is not in the source — that is inventing
regulatory evidence, and it is the one thing this project must never do.

## Adding or changing a source

1. Find the passage on the official site. Working links only.
2. Quote the operative sentence into a chunk with its `locator`.
3. Write the requirement in plain language an exporter can act on.
4. List `checks` only for things a document can actually prove. A requirement
   with no checks is not a failure — it correctly becomes REQUIRES
   VERIFICATION, because we cannot settle it from paperwork alone.
5. Run `pytest tests/test_corpus.py`. It validates every file, every URL
   shape, and every chunk reference.

## Scope

The MVP covers **leather bags exported to Germany**. Sources for other
products or markets do not belong here yet.

## What this corpus is not

It is not legal advice and it is not exhaustive. It is a curated starting
set that lets BAAR-AAMAD show its reasoning with real citations. Final
compliance responsibility stays with the exporter and the authorities.
