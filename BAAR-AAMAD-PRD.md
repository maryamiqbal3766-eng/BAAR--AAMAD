# BAAR-AAMAD — Product Requirements Document

**Product:** AI Export Readiness & Compliance Agent
**Document type:** Hackathon PRD (Generative AI track)
**Version:** 1.2 — September 2026
**Status:** Implemented and verified against live inference. See Section 12.0 for the verification record and Section 12.3 for what remains outside scope.

> **Reading this document.** Section 12.0 records what was measured, on what date, by what means. Everything in Sections 6 to 11 is implemented. Nothing in this document is claimed on the strength of code existing: if a capability is described as verified, Section 12.0 says how. Section 12.3 is future work and is claimed for nothing.

---

## 1. Executive Summary

BAAR-AAMAD is an AI-powered export readiness and compliance agent. An exporter creates an export case (product, origin, destination, parties, shipment details), uploads shipment documents, and BAAR-AAMAD retrieves relevant compliance evidence, checks the documents against it, identifies gaps and inconsistencies, explains each finding, recommends corrective actions, and rechecks the case after corrections are made. The result is an Export Readiness Passport that states what is complete, what needs correction, and what still requires human verification.

The core workflow is:

**FIND → CHECK → EXPLAIN → FIX → RECHECK**

BAAR-AAMAD is designed to use generative AI for evidence interpretation, semantic reasoning, and corrective guidance, while deterministic logic validates exact document facts and unresolved regulatory uncertainty is surfaced for verification rather than converted into false confidence.

---

## 2. Problem Statement

Exporters preparing a shipment must reconcile several sources of difficulty at once:

| Challenge | What it looks like in practice |
|---|---|
| Destination-specific requirements | Rules differ by importing country and change independently of the exporter |
| Product-specific requirements | The same destination imposes different requirements for different goods |
| Documentation requirements | Multiple documents must be present, complete, and mutually consistent |
| Missing information | Required fields or documents are absent and the exporter may not know it |
| Inconsistent information | Quantities, values, descriptions, or parties differ across documents |
| Hard-to-interpret requirements | Regulatory text is dense and rarely mapped to a concrete document checklist |
| Uncertainty about sufficiency | The exporter cannot tell whether the evidence they hold is enough |

These problems are usually handled across disconnected tools, manual reading, and guesswork. The cost of getting it wrong is delayed shipments, rejected documentation, and lost trust with buyers.

---

## 3. Product Vision and Principles

**Vision:** A single workflow where an exporter can see, in plain language, whether their case is ready for the next step of export, what is blocking it, and exactly what to do about it.

**Principles:**

1. **Evidence before interpretation.** Requirements are derived from a curated corpus of authoritative compliance evidence, not generated from model memory.
2. **AI interprets, code verifies.** The LLM reasons over evidence and explains; Python performs exact factual checks and remains authoritative for them.
3. **Uncertainty is a first-class outcome.** When evidence is insufficient, the correct answer is "Verification Required," never an invented conclusion.
4. **Every finding is actionable.** A problem is not finished until the user knows what to do and can recheck.
5. **Transparent provenance.** AI interpretation, retrieved evidence, and deterministic validation are visibly distinguished.
6. **General by design.** Product, origin, and destination are user inputs. No single route, product, or country defines the product.

---

## 4. Target Users

- **Primary:** Exporters and export documentation staff at small and mid-sized businesses who prepare shipment paperwork without dedicated compliance teams.
- **Secondary:** Freight forwarders, customs brokers, and trade consultants who review client documentation before submission.
- **Hackathon audience:** Judges evaluating real LLM usage, RAG-based reasoning, agentic behaviour, trustworthiness, and a working demonstration.

---

## 5. Core User Workflow

1. **Create an export case** — product, origin country, destination country, optional HS code, exporter details, buyer/consignee details, shipment information.
2. **Upload documents** — PDF shipment and compliance documents such as Commercial Invoice, Packing List, and Certificate of Origin.
3. **Find** — the system retrieves relevant evidence from the curated compliance corpus using the case context and assesses coverage.
4. **Check** — requirements are structured from the evidence; documents are converted to structured evidence and validated, including deterministic cross-document consistency checks.
5. **Explain** — each finding states what is wrong, why it matters, what evidence supports it, what to do, and whether verification is needed.
6. **Fix** — the user follows the recommended corrective action and uploads corrected or additional documents.
7. **Recheck** — the pipeline re-runs against the updated inputs and shows what was resolved and what remains outstanding.
8. **Passport** — the Export Readiness Passport summarizes the case, documents reviewed, findings, resolutions, outstanding items, verification-required items, and current readiness status.

---

## 6. Functional Requirements — Current MVP

The following capabilities are implemented in the existing application.

### 6.1 Export Case Management
- FR-1.1 The user can create an export case with product, origin, destination, and shipment/case information.
- FR-1.2 Product, origin, and destination are free user inputs; the case model is not bound to a fixed scenario.

### 6.2 Document Upload and Document Intelligence
- FR-2.1 The user can upload PDF documents to a case.
- FR-2.2 The system extracts information from uploaded documents and produces structured evidence.
- FR-2.3 The system supports document-type handling for Commercial Invoice, Packing List, and Certificate of Origin.
- FR-2.4 Unreadable documents are flagged with an UNREADABLE status and a reupload path.

### 6.3 Compliance Evidence Corpus and Retrieval
- FR-3.1 The application contains a curated corpus of regulatory/compliance evidence.
- FR-3.2 Retrieval is implemented and takes the export case context into account.
- FR-3.3 The application does not claim universal regulatory coverage; retrieval results are bounded by the corpus.

### 6.4 Coverage Assessment
- FR-4.1 Each case is assessed against the corpus using a three-level coverage model: **COVERED**, **PARTIALLY COVERED**, **NOT COVERED**.
- FR-4.2 Where evidence is insufficient, the system requires verification rather than producing a regulatory conclusion.

### 6.5 Requirement Processing
- FR-5.1 Requirements can be generated and structured from the available compliance evidence.
- FR-5.2 Retrieved corpus passages are supplied verbatim to the LLM, which interprets them into structured requirements. The curated requirement wording is deliberately withheld from the model, so this is interpretation of evidence rather than paraphrase of an answer.
- FR-5.3 Every field the model produces passes a grounding gate in Python before use: it must cite at least one passage, every cited passage must have been retrieved for that requirement, and it must not introduce a citation (URL, regulation number, article, annex, entry) absent from the passages supplied. Anything rejected falls back to curated wording and records the reason.
- FR-5.4 Each requirement records whether its wording is AI-interpreted or curated, which passages grounded it, and which fields the model authored. This provenance is user-visible.
- FR-5.5 The model may never author a requirement's structure — its identity, citations, expected document types, deterministic checks, or verification status.

### 6.6 Deterministic Validation
- FR-6.1 Exact document consistency checks are performed in Python.
- FR-6.2 Cross-document comparisons, including quantity consistency, are supported.
- FR-6.3 Deterministic validation is architecturally separate from AI interpretation and remains authoritative for exact facts.

### 6.7 Findings
- FR-7.1 Findings are generated from validation results.
- FR-7.2 Each finding carries one of the following statuses: **COMPLETED**, **ACTION REQUIRED**, **NEEDS CORRECTION**, **VERIFICATION REQUIRED**, **MISSING**, **UNREADABLE**.
- FR-7.3 A finding is structured to answer: what is wrong, why it matters, what evidence supports it, what to do, and whether verification is needed.

### 6.8 Action Plan
- FR-8.1 Findings feed an action-plan flow that provides corrective actions.

### 6.9 Recheck
- FR-9.1 The user can supply corrected or updated documents and re-run the checking pipeline.
- FR-9.2 The recheck output shows whether prior issues are resolved or remain outstanding.
- FR-9.3 The correction/recheck workflow is covered by automated tests.

### 6.10 Export Readiness Passport
- FR-10.1 The application produces a Compliance / Export Readiness Passport summarizing the case, documents, findings, and readiness information.
- FR-10.2 The Passport does not certify legal compliance and states this explicitly.

### 6.11 Human Review and Verification
- FR-11.1 The architecture includes human-review/verification handling.
- FR-11.2 Insufficient evidence is routed to verification and never presented as a confident conclusion.

### 6.12 Error and Failure Handling
- FR-12.1 Structured handling exists for missing documents, unreadable documents, insufficient evidence, AI service failure, and other pipeline failures.
- FR-12.2 On AI failure, the pipeline falls back to deterministic processing where supported.

---

## 7. Responsible AI Architecture

BAAR-AAMAD separates responsibilities across four layers so that no single component can produce an unsupported compliance verdict.

| Layer | Responsibility | Authority |
|---|---|---|
| **Evidence** | Curated corpus of authoritative compliance material, retrieved per case | Basis for all requirements |
| **AI reasoning** | Interpret retrieved evidence, read semi-structured document data, semantic comparison, explain findings, generate corrective actions, summarize readiness, decide what to check next | Interpretation and explanation only |
| **Deterministic validation** | Exact factual checks (field presence, cross-document consistency such as quantities) | Authoritative for exact facts |
| **Human review** | Resolve items where evidence is insufficient or ambiguous | Final say on uncertainty |

**RAG flow:**

```
Export case
  → Retrieve relevant evidence (curated corpus, case-aware)
  → Authoritative source evidence
  → AI interpretation
  → Structured requirement
  → Document / evidence check (deterministic where exact)
  → Finding (with status, evidence, action, verification flag)
```

**Non-fabrication rule.** The system must never invent laws, regulations, requirements, authorities, citations, or sources. When retrieval does not yield sufficient evidence, the outcome is VERIFICATION REQUIRED.

---

## 8. Generative AI and Agentic Design

### 8.1 Role of the LLM
The LLM (openai/gpt-oss-120b via the Groq API) is designed to:
- interpret retrieved compliance evidence into structured requirements
- understand semi-structured document information
- perform semantic comparison where exact matching is insufficient
- explain findings in plain language
- identify missing information
- generate corrective actions
- summarize readiness
- decide what information or check may be needed next

The LLM is not the sole authority for compliance verdicts. Exact checks remain deterministic; the AI explains their significance and recommends action.

**Implementation status.** Six call sites run through a single gateway (`core/llm.py`): product description, evidence interpretation, document field gap-filling, agent tool selection, semantic comparison, and finding explanation. Both tiers resolve to `openai/gpt-oss-120b`, so one identifiable model answers every call. Each call is recorded — call site, model that served it, latency, tokens, outcome — and that ledger is rendered in the AI Activity view. Model reasoning is suppressed at the transport (`reasoning_format="hidden"`), so chain-of-thought never enters the process.

Every call site degrades to a deterministic path on failure or absent key, and the fallback is recorded rather than silent. The application therefore runs end to end with or without AI, validated by the automated test suite.

### 8.2 Agentic Behaviour
BAAR-AAMAD is designed to operate as a bounded agent rather than a single chatbot call:

```
PLAN → USE TOOL → OBSERVE → DECIDE → ACT / VERIFY
```

The agent understands the case, determines what evidence or check is relevant, selects an available tool, observes the result, and decides whether another check is needed. Tool selection is constrained to the available checks; the LLM cannot invent regulatory conclusions outside that boundary.

**Implementation status.** Implemented as ONE bounded loop in `core/agent.py` — not a multi-agent framework. The model chooses a single tool per turn from a fixed five-tool menu (`list_documents`, `read_document_fields`, `run_requirement_checks`, `compare_field_across_documents`, `finish`), Python executes it, and the observation returns to the model for the next decision.

**Bounds, all enforced in Python rather than requested in a prompt:**

| Bound | Effect |
|---|---|
| Step limit | The loop stops after a fixed number of turns whatever the model does |
| Call limit | A separate ceiling on model calls per run |
| Fixed tool menu | Any other tool name is refused |
| Argument validation | A document type, field or requirement not present on the case is refused |

A refusal is not an error: it becomes an observation, returns to the model, and the loop continues. The model may ask for anything; only permitted things happen.

**Why the agent cannot bypass a mandatory check.** It does not produce verdicts. After the loop finishes — however it finishes, including failing outright — the orchestrator runs the full deterministic validation pass over every requirement, unconditionally and without reading the investigation. The agent's influence on the outcome is bounded at zero by construction rather than by audit. What it adds is investigation and a visible account of it.

---

## 9. Trust and Safety Requirements

| Condition | Required system behaviour |
|---|---|
| Evidence insufficient | Status **VERIFICATION REQUIRED** — no invented answer |
| Document unreadable | Status **UNREADABLE** — prompt reupload |
| Information missing | Status **MISSING / INFORMATION REQUIRED** |
| Documents contradict each other | Status **NEEDS CORRECTION** with the specific inconsistency identified |
| AI service unavailable | Graceful fallback to deterministic checks where supported |
| Any output | AI-generated interpretation is visibly distinguished from evidence and deterministic validation |
| Passport | Never certifies legal compliance |

- TS-1 The API key is read from the environment — a local `.env` (git-ignored) or Streamlit Secrets. It is never hard-coded, never logged, never written into a case, and never printed by the diagnostic script, which reports only whether a key is present.
- TS-2 The system does not expose model chain-of-thought to users. Enforced at the transport rather than by prompt: the gateway sets `reasoning_format="hidden"`, so reasoning content never enters the process. The call ledger records metadata only — no prompts, no completions, no reasoning.
- TS-3 The system does not claim universal regulatory coverage.
- TS-4 A deterministic fallback is recorded as an observable event. A stage that did not call the model because no key was configured must not be indistinguishable, in the interface, from a stage that ran.

---

## 10. Non-Functional Requirements

- NFR-1 **Deployability:** Runs on Streamlit Community Cloud. The API key is supplied through Streamlit Secrets.
- NFR-2 **Robustness:** The pipeline completes on deterministic paths when the AI service fails or is rate-limited, and each fallback is recorded rather than silent. **Verified: 409 tests passing, 0 failed, 0 skipped**, including 5 live-inference tests.
- NFR-3 **Reproducibility:** A prepared demonstration scenario exists so the hackathon demo is repeatable. This scenario is a fixture only and does not define product scope.
- NFR-4 **Generality:** No hard-coded product, origin, destination, or route anywhere in application code. **Verified live** against a product outside the demo scenario (Section 12.0).
- NFR-5 **Transparency:** Provenance of each finding (retrieved passage, AI interpretation, deterministic check) is traceable and rendered. **Verified: 56/56 end-to-end checks**, including that no chain-of-thought or prompt text reaches any surface.
- NFR-6 **Latency:** ~17 seconds per run with AI enabled, 7 model calls. Measured, not estimated (Section 12.0).
- NFR-7 **Accessibility:** Permanently light interface; every text colour meets WCAG AA contrast on every background it is used on, enforced by test.

---

## 11. Technology Stack

| Component | Technology |
|---|---|
| Language | Python |
| UI / app framework | Streamlit |
| LLM access | Groq API |
| LLM model | openai/gpt-oss-120b |
| Document processing | PDF / document extraction |
| Knowledge layer | Curated compliance evidence corpus with retrieval (RAG) |
| Validation | Deterministic Python checks |
| Agent | One bounded tool-selection loop with Python-enforced limits |
| Secrets | Environment variable; Streamlit Secrets when deployed, a git-ignored `.env` locally |
| Hosting | Streamlit Community Cloud |
| Quality | Automated test suite — 409 passing, 0 failed, 0 skipped, of which 5 exercise live inference |

---

## 12. Verification Record and Roadmap

### 12.0 Verification record

Measured on **13 September 2026** against `openai/gpt-oss-120b` on the Groq API, with a real key in the environment. These are results, not intentions.

#### Test results

| Suite | Result |
|---|---|
| Live inference — `tests/test_llm_live.py` | **5 / 5 passed** |
| Full automated suite | **409 passed, 0 failed, 0 skipped** (45 s) |
| End-to-end live walkthrough | **56 / 56 checks passed** |

The 409 figure is the whole suite including the 5 live tests. The suite does not reach the network unless a test asks to: an autouse fixture removes the key from the environment unless a test is marked `live` or installs a fake client. A suite whose result depends on whether a key happens to be exported is not measuring anything.

#### What the live walkthrough exercised

The walkthrough drove the running Streamlit application with AI enabled and no mocking, through FIND → CHECK → EXPLAIN → FIX → RECHECK.

| Capability | Verified behaviour |
|---|---|
| **RAG → LLM grounding** | All 5 retrieved requirements were interpreted by the live model, 0 curated fallbacks. Each was grounded **only in its own retrieved passages** — e.g. `REQ-CHROMIUM-VI` cited `eu-reach-301-2014#entry47p5`; `REQ-PROOF-OF-ORIGIN` cited its three GSP/REX passages. No requirement was supported by another requirement's evidence. |
| **Bounded agent loop** | Ran 4 steps, every tool drawn from the fixed menu, decisions recorded `CONTINUE → CONTINUE → CONTINUE → STOP`. It chose to list the documents, then check requirements in turn, and located the quantity contradiction itself. The Python step limit held. |
| **Deterministic authority** | Findings from the live-AI run were **identical** — state, label and priority for every requirement — to a deterministic-only run of the same case. Case status matched. The agent changed nothing, as designed. |
| **Findings and explanations** | 5 findings, each with label, priority, what was found and a next action; 5 explanations, each with a conclusion. |
| **Coverage visibility** | Assessed COVERED and rendered on the dashboard. |
| **Activity view** | Model named, retrieved passages shown beside the requirements they produced, AI-interpreted badges present, agent trace and decisions shown, call ledger shown. **Zero chain-of-thought markers, no prompt text, and no prompts or completions in the stored call records.** |
| **Passport** | Generated; quotes the exporter's own product wording; states case status; discloses coverage; 5-row evidence map; no percentage score. Plain-text form states coverage before requirements. |
| **Correction → recheck** | After replacing the packing list with the corrected copy, run 2 completed, the contradiction was resolved, and status moved ACTION REQUIRED → VERIFICATION REQUIRED. Activity was rebuilt for the run rather than appended to. |
| **Product-agnostic behaviour** | A *cotton garments* case, Pakistan → Germany, was assessed **PARTIALLY COVERED**, retrieved the 4 route-level customs requirements, had all 4 interpreted live, and **correctly refused to claim the leather chromium rule**. The unassessed product-specific rules were named explicitly. The exporter's own wording was stored unchanged and no category was invented. |

#### On the demonstration fixture

The walkthrough used the prepared demonstration documents — an invoice and packing list that disagree on quantity, plus a certificate of origin — because a repeatable demo needs a known contradiction to find. **That fixture is a test artefact, not the product's scope.** The product-agnostic row above was run on entirely different goods against the same corpus, and is the row that speaks to generality.

#### Measured performance

| Measure | Value |
|---|---|
| Pipeline wall time, AI enabled | **~17 seconds** per run |
| Model calls per run | 7 |
| Tokens per run | ~11,000 |

Latency is dominated by evidence interpretation and finding explanation. The agent loop is capped at 4 steps: at 8 it cost roughly twice the tokens and time while establishing nothing the first four had not, since each turn resends the whole observation history.

#### Operational constraint

~11,000 tokens per run exceeds the Groq free tier's 8,000 tokens-per-minute allowance. Consecutive runs within one minute will be rate-limited. This does not break the pipeline — calls degrade to the deterministic path and the fallback is recorded and visible — but AI participation is reduced while the limit is in force. A paid tier removes the constraint. See Section 15.

### 12.1 Hackathon completion items

All items below are implemented. The Verified column says what Section 12.0 actually measured.

| Item | Implementation | Verified |
|---|---|---|
| **Live LLM execution** | Both tiers resolve to `openai/gpt-oss-120b`; reasoning suppressed at the transport; unsupported-parameter degradation; per-call ledger. `scripts/check_llm.py` performs a live round-trip and reports PASS / FAILED / NOT TESTED — it never reports a pass it did not measure. | ✅ 5/5 live tests; live round-trip returning validated structured output |
| **RAG → LLM interpretation** | Retrieved passages sent verbatim; curated wording withheld; grounding gate rejects ungrounded or invented-citation output per requirement. See FR-5.2 to FR-5.5. | ✅ 5/5 requirements interpreted live, each grounded only in its own passages |
| **Agentic loop** | One bounded loop, fixed tool menu, Python-enforced limits, deterministic validation running in full afterwards. See Section 8.2. | ✅ 4 steps, tool → observation → decision recorded, limits held |
| **Deterministic authority** | The full validation pass runs after the loop, unconditionally, and does not read the investigation. | ✅ Live-AI verdicts identical to deterministic-only verdicts |
| **AI / Agent Activity view** | Model, coverage, retrieved passage → interpretation → requirement, agent trace, and the per-call ledger including every deterministic fallback. | ✅ All panels present; zero chain-of-thought and no prompt text |
| **Coverage visibility** | Three-tone banner with an explicit "not assessed" list on dashboard, action plan, Activity view and Passport; level travels on the Passport object and its plain-text form. | ✅ Rendered; disclosed on the Passport; partial coverage names what went unassessed |
| **Correction → recheck** | The same pipeline re-runs; every stage rebuilds its own output. | ✅ Run 2 resolved the contradiction; status improved; activity rebuilt, not appended |
| **Product-agnostic understanding** | No product vocabulary in application code. Python tidies the exporter's words and invents no category; sources declare the goods they cover and retrieval matches against those declarations. | ✅ Cotton-garments case: PARTIALLY COVERED, leather rule correctly refused, wording preserved |
| **Permanent light theme** | Enforced in three places (`config.toml` base, `color-scheme: light only`, explicit dark-mode block re-stating the palette). No toggle. | ✅ Every text colour measured against WCAG AA on every ground, by test |

### 12.2 Known constraints

These are real and measured, not defects to be explained away.

| Constraint | Detail |
|---|---|
| **Rate limit on the free tier** | ~11,000 tokens per run against an 8,000 TPM allowance. Consecutive runs inside a minute are throttled; calls degrade to the deterministic path and the fallback is recorded and visible. A paid tier removes it. |
| **Pipeline latency** | ~17 seconds per run with AI enabled. Acceptable for a considered compliance check; it is not an instant interaction and should not be presented as one. |
| **Corpus breadth** | Three curated sources. Coverage grading states the limits per case rather than implying more. Widening is curation work, not code. |

### 12.3 Future roadmap (out of scope)
Not part of the current product, not implemented, and claimed for nothing:

- Fully autonomous multi-agent system
- Unrestricted autonomous regulatory research
- Web-scale regulatory retrieval
- Automatic legal certification or guaranteed legal compliance
- Universal regulatory coverage for every product and destination
- Persistent database-backed enterprise case management
- Authentication and user management
- Enterprise integrations
- Payment and billing
- Automated government submission
- Production-grade global regulatory coverage

---

## 13. Success Criteria

Every criterion below has been met and measured. Evidence is in Section 12.0.

**Product:**

| Criterion | Status |
|---|---|
| A user can create a general export case, upload documents, receive structured findings with clear statuses, follow corrective actions, recheck, and obtain a Passport | ✅ Met — walked end to end live |
| Insufficient evidence consistently yields VERIFICATION REQUIRED | ✅ Met — a requirement with no document-settleable check resolves to verification, and the recheck case ended VERIFICATION REQUIRED rather than claiming compliance |
| The pipeline completes on fallback paths when AI is unavailable | ✅ Met — 404 of the 409 tests run with AI disabled; rate-limited calls degraded without breaking a run |
| Product, origin and destination are genuinely free inputs | ✅ Met — verified live on a product outside the demo scenario |

**Hackathon:**

| Criterion | Status |
|---|---|
| Live LLM call demonstrated | ✅ **5/5 live tests passed**; `scripts/check_llm.py` returns PASS only on a real round-trip and NOT TESTED when no key is present |
| Retrieved evidence visibly informs an AI-interpreted requirement | ✅ **5/5 requirements interpreted live**, each grounded only in its own retrieved passages, shown passage-beside-requirement in the Activity view |
| At least one agent decision (tool → observation → next decision) visible | ✅ **4 steps** recorded with tool, arguments, intent, observation and decision |
| A reproducible demo runs FIND → CHECK → EXPLAIN → FIX → RECHECK end to end | ✅ **56/56 end-to-end checks passed** against the running application with live inference |
| The AI cannot quietly change a compliance verdict | ✅ Live-AI findings identical to deterministic-only findings |

---

## 14. Alignment with Judging Dimensions

| Judging dimension | How BAAR-AAMAD addresses it | Verified |
|---|---|---|
| API integration | Groq API through a single gateway; key from environment or Streamlit Secrets, never in source | 5/5 live tests |
| Real LLM usage | `openai/gpt-oss-120b` serving both tiers — evidence interpretation, product description, field gap-filling, agent tool selection, semantic comparison, finding explanation | 7 live calls per run, each recorded with the model that served it |
| RAG-based reasoning | Curated corpus, case-aware retrieval, passages sent verbatim to the model, grounding gate over what comes back, three-level coverage model | 5/5 requirements interpreted live and grounded in their own passages |
| Agentic AI | One bounded plan → tool → observe → decide loop over a fixed tool menu, with Python-enforced limits | 4 steps, decisions recorded, limits held |
| Real-world problem and impact | Export documentation readiness for SMEs, forwarders, and brokers | — |
| Technical implementation | Separated evidence / AI / deterministic / human layers; structured failure handling; offline-by-default test suite | 409 passing, 0 failed, 0 skipped |
| Trustworthy / safe AI | Non-fabrication rule enforced mechanically; VERIFICATION REQUIRED as a first-class outcome; AI and curated wording visibly distinguished; no chain-of-thought collected; no false certification | Live-AI verdicts identical to deterministic; zero CoT on any surface |
| Demonstrable working product | Streamlit application, reproducible demo fixture, correction and recheck workflow | 56/56 end-to-end checks |

---

## 15. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| LLM unavailable during demo | Deterministic fallback path keeps the pipeline functional, and the Activity view states plainly that the model did not run |
| **Rate limit reached mid-demo** | Measured: ~11,000 tokens per run against an 8,000 TPM free-tier allowance. Calls degrade to the deterministic path rather than failing the run. Mitigations, in order of preference: a paid tier; or leaving roughly a minute between runs during a demo |
| **Latency mistaken for a hang** | ~17 seconds per run with AI enabled. The processing screen names each stage as it completes, so progress is visible rather than a blank wait |
| Model produces an unsupported regulatory claim | Evidence-first RAG design; grounding gate rejects invented citations mechanically; deterministic authority for exact facts; VERIFICATION REQUIRED default |
| Model quietly changes a verdict | Structurally impossible: deterministic validation runs in full after the agent and does not read it. Verified by comparing live-AI findings to deterministic-only findings |
| Corpus does not cover a case | Coverage model exposes NOT COVERED / PARTIALLY COVERED and names what went unassessed, instead of guessing |
| Judges cannot see AI activity | AI & Agent Activity view (Sections 12.0, 12.1) |
| Over-claiming capability | Section 12.0 records what was measured; Sections 12.2 and 12.3 record constraints and non-goals. No capability is asserted on the strength of code existing |

---

## 16. Glossary

- **Export case** — The user-defined unit of work: product, origin, destination, parties, shipment details, and documents.
- **Evidence** — Retrieved content from the curated compliance corpus, or structured data extracted from uploaded documents.
- **Coverage** — The degree to which the corpus addresses a case: COVERED, PARTIALLY COVERED, NOT COVERED.
- **Finding** — A structured result with status, explanation, supporting evidence, recommended action, and verification flag.
- **Recheck** — Re-running the pipeline on updated inputs to determine what has been resolved.
- **Export Readiness Passport** — The summary output of a case; not a legal compliance certificate.
- **Grounding gate** — The Python check every AI-written requirement field passes before use: it must cite a retrieved passage, cite only passages retrieved for that requirement, and introduce no citation absent from them. Failing it means the curated wording is shown and the reason recorded.
- **Bounded agent loop** — The single plan → tool → observe → decide loop. Bounded by a fixed tool menu, Python-enforced step and call limits, and argument validation against the case. It investigates; it decides no verdict.
- **Call ledger** — The per-run record of every model call: call site, model that served it, latency, tokens and outcome. Holds no prompts, completions or reasoning, because it is rendered on screen.
- **Demonstration fixture** — The prepared documents used to make the demo repeatable. A test artefact; it does not define what the product supports.
