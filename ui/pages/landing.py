"""Landing screen. States what the tool does, what it covers, and starts a case."""

from __future__ import annotations

import streamlit as st

from core import state
from ui.pages.create_case import SUPPORTED_DESTINATIONS, SUPPORTED_PRODUCTS
from modules.corpus import get_corpus
from ui import theme

#: The three questions an exporter actually has, in the order they have them.
HOW_IT_WORKS = [
    (
        "Find",
        "What does this shipment actually need?",
        "BAAR-AAMAD searches curated authoritative sources for the "
        "requirements that apply to your product and your destination — and "
        "tells you plainly where it has no source to rely on.",
    ),
    (
        "Check",
        "Do my documents satisfy them?",
        "Your invoice, packing list and certificate are read, the values "
        "pulled out, and each requirement checked against what they really "
        "say — including whether your own documents agree with each other.",
    ),
    (
        "Explain",
        "Why was this flagged?",
        "Every finding shows the requirement, the source passage it came "
        "from, the values read from your documents, and how the comparison "
        "came out. No verdict without its evidence.",
    ),
    (
        "Fix",
        "What do I do about it?",
        "An action plan ordered by urgency, a checklist of what is missing, "
        "and — where a document is absent — a preparation worksheet built "
        "only from facts already in your case.",
    ),
    (
        "Recheck",
        "Is it resolved?",
        "Upload the corrected document and run the case again. Findings, "
        "readiness and your Compliance Passport all update.",
    ),
]


def _how_it_works() -> None:
    for step, question, body in HOW_IT_WORKS:
        st.markdown(
            f'<div class="ba-chain">'
            f'<div class="ba-chain-step">{step}</div>'
            f'<div class="ba-finding-head">{question}</div>'
            f'<div class="ba-finding-body">{body}</div></div>',
            unsafe_allow_html=True,
        )


def _sources() -> None:
    """Name the actual sources. Credibility comes from being checkable."""
    try:
        corpus = get_corpus()
    except Exception:
        theme.note("The authoritative source library could not be loaded.")
        return

    for source in corpus.sources.values():
        st.markdown(
            f'<div class="ba-source">'
            f'<a href="{source.source_url}" target="_blank" rel="noopener">'
            f"{source.source_name}</a> &middot; {source.publisher}</div>",
            unsafe_allow_html=True,
        )


def render() -> None:
    theme.masthead("AI EXPORT READINESS &amp; COMPLIANCE AGENT")

    st.markdown(
        '<div class="ba-eyebrow">For Pakistani exporters</div>'
        '<div class="ba-h1">Know what your export needs<br>before your '
        "shipment is stopped.</div>"
        '<div class="ba-lede">BAAR-AAMAD reads the authoritative requirements '
        "for your product and destination, reads your own documents, and "
        "tells you exactly what is missing, what contradicts, and what to do "
        "about it — with the source for every conclusion.</div>",
        unsafe_allow_html=True,
    )

    theme.workflow_strip()

    left, right = st.columns([1, 1.3])
    with left:
        if st.button("Start an export case", type="primary", width="stretch"):
            state.goto(state.Page.CREATE_CASE)
            st.rerun()
    with right:
        if state.has_case():
            case = state.current_case()
            if st.button(f"Return to case {case.case_id}", width="stretch"):
                state.goto(
                    state.Page.DASHBOARD if case.findings else state.Page.CASE_CREATED
                )
                st.rerun()

    theme.section("How it works")
    _how_it_works()

    theme.section("What this release covers")
    theme.kv_table(
        [
            ("Products", ", ".join(SUPPORTED_PRODUCTS)),
            (
                "Destinations",
                f"All {len(SUPPORTED_DESTINATIONS)} European Union member "
                f"states, including {', '.join(SUPPORTED_DESTINATIONS[:3])} "
                "and Germany",
            ),
            ("Documents", "Commercial Invoice, Packing List, Certificate of Origin"),
        ]
    )
    theme.note(
        "Other products and markets are not covered yet. BAAR-AAMAD will say "
        "so plainly rather than assemble a requirement list it cannot support."
    )

    theme.section("Where the requirements come from")
    _sources()
    theme.note(
        "Every requirement BAAR-AAMAD states is traced to one of these "
        "sources, quoted with a link you can open. Where the sources do not "
        "settle a question, it is marked for human verification instead of "
        "being answered. <b>BAAR-AAMAD never invents a regulation.</b>"
    )

    theme.disclaimer()
