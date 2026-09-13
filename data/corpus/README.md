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
  "applies_to":  {
    // MATCHING VOCABULARY, not a display list. Each entry is a wording an
    // exporter might use for the goods this source covers. An entry matches a
    // case only when EVERY word of it appears in the exporter's own product
    // description, so "leather bags" matches "handmade leather shoulder bags"
    // but "bags" alone never reaches a leather source — we would not know
    // what those bags are made of. Use "any goods" for a source that does not
    // narrow by product at all.
    "products": ["leather articles", "leather bags", "leather handbags"],
    // Optional. How to NAME that scope to a person, since reading two dozen
    // wordings aloud tells nobody anything. Falls back to the list.
    "scope_label": "leather articles that touch the skin",
    "origins":      ["any origin"],       // omit and it means any origin
    "destinations": ["European Union"]    // a bloc covers its member states
  },

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
5. Run `pytest tests/test_intelligence.py tests/test_scope.py`. Between them
   they validate every file, every URL shape, every chunk reference, and that
   the product gate still refuses goods the source was not written for.

## Scope lives here, and only here

**This directory is the application's scope.** There is no list of supported
products or markets anywhere in the code — not in `core/schemas.py`, not in
`modules/profile.py`, not in an error message. What BAAR-AAMAD can advise on
is computed per case from what these files declare, and graded COVERED /
PARTIALLY COVERED / NOT COVERED.

That is why widening the product is a curation job rather than a code change:
add a real source for the goods, with real passages, and cases for those goods
start being covered. It is also why nothing may be widened without one. A
product with no source is not refused — general route-level sources may still
apply — but the parts that went unassessed are named explicitly rather than
guessed at.

Leather bags from Pakistan to Germany is the reproducible DEMO scenario. It is
a test case, not the product's scope.

## What this corpus is not

It is not legal advice and it is not exhaustive. It is a curated starting
set that lets BAAR-AAMAD show its reasoning with real citations. Final
compliance responsibility stays with the exporter and the authorities.
