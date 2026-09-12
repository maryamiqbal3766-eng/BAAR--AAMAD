"""
BAAR-AAMAD — VISUAL LANGUAGE
============================

One restrained palette and a small set of components, injected once per run.

The target is a professional international-trade / fintech tool: quiet
colours, generous whitespace, documentary typography. Deliberately not a
chatbot, and deliberately not decorated.
"""

from __future__ import annotations

import streamlit as st

INK = "#0F1C24"
MUTED = "#5C6B76"
LINE = "#E3E7EA"
PANEL = "#F7F9FA"
ACCENT = "#0E4F5C"

CSS = f"""
<style>
  /* --- strip Streamlit chrome ------------------------------------------- */
  #MainMenu, footer, [data-testid="stToolbar"] {{ visibility: hidden; height: 0; }}
  [data-testid="stDecoration"] {{ display: none; }}
  .block-container {{ padding-top: 2.6rem; padding-bottom: 4rem; max-width: 900px; }}

  html, body, [class*="css"] {{ color: {INK}; }}

  /* --- masthead ---------------------------------------------------------- */
  .ba-mast {{
    display: flex; align-items: baseline; justify-content: space-between;
    border-bottom: 1px solid {LINE}; padding-bottom: .7rem; margin-bottom: 2rem;
  }}
  .ba-mark {{
    font-size: 1.05rem; font-weight: 700; letter-spacing: .14em;
    color: {INK}; text-transform: uppercase;
  }}
  .ba-mark span {{ color: {ACCENT}; }}
  .ba-mast-meta {{
    font-family: ui-monospace, "SFMono-Regular", Consolas, monospace;
    font-size: .74rem; letter-spacing: .08em; color: {MUTED};
  }}

  /* --- type -------------------------------------------------------------- */
  .ba-eyebrow {{
    font-size: .68rem; font-weight: 700; letter-spacing: .18em;
    text-transform: uppercase; color: {MUTED}; margin-bottom: .55rem;
  }}
  .ba-h1 {{
    font-size: 2.35rem; line-height: 1.15; font-weight: 700;
    letter-spacing: -.02em; margin: 0 0 .9rem 0; color: {INK};
  }}
  .ba-lede {{
    font-size: 1.02rem; line-height: 1.65; color: {MUTED};
    max-width: 60ch; margin-bottom: 2.1rem;
  }}
  .ba-h2 {{
    font-size: .72rem; font-weight: 700; letter-spacing: .16em;
    text-transform: uppercase; color: {MUTED};
    padding-bottom: .5rem; border-bottom: 1px solid {LINE};
    margin: 2.1rem 0 1.1rem 0;
  }}

  /* --- workflow strip ---------------------------------------------------- */
  .ba-flow {{
    display: flex; flex-wrap: wrap; gap: .45rem; align-items: center;
    margin: 0 0 2.4rem 0;
  }}
  .ba-step {{
    font-family: ui-monospace, "SFMono-Regular", Consolas, monospace;
    font-size: .68rem; letter-spacing: .12em; text-transform: uppercase;
    padding: .36rem .7rem; border: 1px solid {LINE}; border-radius: 3px;
    color: {MUTED}; background: #fff;
  }}
  .ba-step.is-now {{
    color: #fff; background: {ACCENT}; border-color: {ACCENT}; font-weight: 600;
  }}
  .ba-arrow {{ color: {LINE}; font-size: .8rem; }}

  /* --- case header ------------------------------------------------------- */
  .ba-caseid {{
    font-family: ui-monospace, "SFMono-Regular", Consolas, monospace;
    font-size: 2.5rem; font-weight: 700; letter-spacing: .02em;
    color: {INK}; line-height: 1;
  }}
  .ba-pill {{
    display: inline-block; font-family: ui-monospace, Consolas, monospace;
    font-size: .67rem; letter-spacing: .13em; text-transform: uppercase;
    padding: .32rem .66rem; border-radius: 3px;
    border: 1px solid {LINE}; background: {PANEL}; color: {MUTED};
  }}

  /* --- key / value rows -------------------------------------------------- */
  .ba-kv {{ border-top: 1px solid {LINE}; }}
  .ba-row {{
    display: flex; gap: 1.5rem; padding: .68rem 0;
    border-bottom: 1px solid {LINE}; font-size: .9rem;
  }}
  .ba-key {{
    flex: 0 0 12rem; color: {MUTED}; font-size: .72rem; font-weight: 600;
    letter-spacing: .1em; text-transform: uppercase; padding-top: .12rem;
  }}
  .ba-val {{ flex: 1 1 auto; color: {INK}; }}
  .ba-val.is-empty {{ color: #A3AEB6; font-style: italic; }}

  /* --- document slots ---------------------------------------------------- */
  .ba-slot-key {{
    color: {MUTED}; font-size: .72rem; font-weight: 600; letter-spacing: .1em;
    text-transform: uppercase; padding: .85rem 0 0 0;
  }}
  .ba-slot-val {{ color: {INK}; font-size: .9rem; padding: .8rem 0 0 0; }}
  .ba-slot-val.is-empty {{ color: #A3AEB6; font-style: italic; }}
  .ba-slot-val.ba-unreadable {{ color: #A6472E; }}
  .ba-slot-meta {{
    display: block; font-family: ui-monospace, Consolas, monospace;
    font-size: .68rem; letter-spacing: .06em; color: {MUTED};
    text-transform: uppercase; margin-top: .18rem;
  }}

  /* --- notes ------------------------------------------------------------- */
  .ba-note {{
    border-left: 2px solid {LINE}; padding: .1rem 0 .1rem .9rem;
    color: {MUTED}; font-size: .84rem; line-height: 1.6; margin: 1.2rem 0;
  }}
  .ba-note.is-scope {{ border-left-color: #C4903B; }}

  .ba-foot {{
    margin-top: 3.2rem; padding-top: 1rem; border-top: 1px solid {LINE};
    color: {MUTED}; font-size: .76rem; line-height: 1.6;
  }}

  /* --- pipeline progress -------------------------------------------------- */
  .ba-stage {{
    padding: .5rem 0 .5rem .95rem; border-left: 2px solid {LINE};
    font-size: .88rem; color: {MUTED}; margin-bottom: .1rem;
  }}
  .ba-stage.is-done {{ border-left-color: {ACCENT}; color: {INK}; }}
  .ba-stage.is-failed {{ border-left-color: #A6472E; color: #A6472E; }}
  .ba-stage-note {{
    display: block; font-family: ui-monospace, Consolas, monospace;
    font-size: .68rem; letter-spacing: .04em; color: {MUTED}; margin-top: .15rem;
  }}

  /* --- case status -------------------------------------------------------- */
  .ba-status {{
    display: inline-block; font-family: ui-monospace, Consolas, monospace;
    font-size: 1.05rem; font-weight: 700; letter-spacing: .1em;
    padding: .55rem 1rem; border-radius: 3px; margin-bottom: 1rem;
    border: 1px solid {LINE}; background: {PANEL}; color: {INK};
  }}
  .ba-status.is-action {{ border-color:#A6472E; color:#A6472E; background:#FDF6F4; }}
  .ba-status.is-verify {{ border-color:#B4832F; color:#8A621F; background:#FDFAF3; }}
  .ba-status.is-ready  {{ border-color:{ACCENT}; color:{ACCENT}; background:#F2F8F9; }}

  /* --- tally -------------------------------------------------------------- */
  .ba-tally {{ display: flex; flex-wrap: wrap; gap: 1.8rem; margin: .4rem 0 1rem; }}
  .ba-tally-n {{ display:block; font-size:1.7rem; font-weight:700; color:{INK}; }}
  .ba-tally-l {{
    font-size: .7rem; letter-spacing: .1em; text-transform: uppercase;
    color: {MUTED};
  }}

  /* --- priority bands ----------------------------------------------------- */
  .ba-band {{
    margin: 1.8rem 0 .7rem; padding-bottom: .4rem;
    border-bottom: 1px solid {LINE};
  }}
  .ba-band-name {{
    font-family: ui-monospace, Consolas, monospace; font-size: .72rem;
    font-weight: 700; letter-spacing: .14em; color: {INK};
  }}
  .ba-band-sub {{ font-size: .72rem; color: {MUTED}; margin-left: .7rem; }}

  /* --- findings ----------------------------------------------------------- */
  .ba-finding {{ padding: .7rem 0; }}
  .ba-finding-head {{ font-size: .95rem; font-weight: 600; color: {INK}; }}
  .ba-glyph {{ font-family: ui-monospace, Consolas, monospace; margin-right:.3rem; }}
  .ba-finding-label {{
    font-family: ui-monospace, Consolas, monospace; font-size: .62rem;
    letter-spacing: .1em; text-transform: uppercase; color: {MUTED};
    border: 1px solid {LINE}; border-radius: 3px; padding: .12rem .4rem;
    margin-left: .6rem; white-space: nowrap;
  }}
  .ba-finding-body {{ font-size: .87rem; color: {MUTED}; margin-top: .25rem; }}

  /* --- prose -------------------------------------------------------------- */
  .ba-para {{ font-size: .92rem; line-height: 1.65; color: {INK}; margin:.2rem 0 .6rem; }}
  .ba-para.is-muted {{ color: {MUTED}; font-size: .86rem; }}
  .ba-bullet {{
    font-size: .9rem; color: {INK}; padding: .22rem 0 .22rem .95rem;
    border-left: 2px solid {LINE};
  }}
  .ba-numbered {{ font-size: .92rem; color: {INK}; padding: .35rem 0; }}
  .ba-numbered span {{
    display: inline-block; width: 1.4rem; font-family: ui-monospace, Consolas, monospace;
    color: {MUTED}; font-size: .78rem;
  }}
  .ba-source {{ font-size: .85rem; padding: .3rem 0; }}
  .ba-source a {{ color: {ACCENT}; }}

  /* --- evidence chain ------------------------------------------------------ */
  .ba-chain {{
    border-left: 2px solid {LINE}; padding: .1rem 0 .8rem .95rem; margin-bottom:.2rem;
  }}
  .ba-chain-step {{
    font-family: ui-monospace, Consolas, monospace; font-size: .66rem;
    letter-spacing: .12em; text-transform: uppercase; color: {ACCENT};
    margin-bottom: .25rem;
  }}
  .ba-chain-body {{
    font-size: .88rem; line-height: 1.6; color: {INK}; white-space: pre-wrap;
  }}

  /* --- action plan --------------------------------------------------------- */
  .ba-action {{ display: flex; gap: .9rem; padding: .9rem 0; }}
  .ba-action-n {{
    flex: 0 0 1.6rem; font-family: ui-monospace, Consolas, monospace;
    font-size: .85rem; color: {MUTED}; padding-top: .12rem;
  }}
  .ba-action-main {{ flex: 1 1 auto; }}
  .ba-action-problem {{ font-size: .95rem; font-weight: 600; color: {INK}; }}
  .ba-action-row {{ font-size: .87rem; color: {MUTED}; margin-top: .3rem; }}
  .ba-action-row b {{
    display: block; font-size: .66rem; letter-spacing: .1em;
    text-transform: uppercase; color: {INK}; margin-bottom: .1rem;
  }}
  .ba-action-provide b {{
    font-size: .66rem; letter-spacing: .1em; text-transform: uppercase;
    color: {INK};
  }}
  .ba-draft-banner {{
    font-family: ui-monospace, Consolas, monospace; font-size: .72rem;
    font-weight: 700; letter-spacing: .12em; color: #8A621F;
    background: #FDFAF3; border: 1px solid #E4D4AE; border-radius: 3px;
    padding: .5rem .7rem; margin-bottom: .7rem;
  }}

  /* --- evidence map -------------------------------------------------------- */
  .ba-map {{
    border-top: 1px solid {LINE}; padding: .8rem 0;
  }}
  .ba-map-req {{ font-size: .92rem; font-weight: 600; color: {INK}; }}
  .ba-map-row {{ font-size: .84rem; color: {MUTED}; margin-top: .28rem; }}
  .ba-map-row b {{
    display: inline-block; min-width: 8.5rem; font-size: .64rem;
    letter-spacing: .1em; text-transform: uppercase; color: {INK};
  }}
  .ba-map-row a {{ color: {ACCENT}; }}

  /* --- controls ---------------------------------------------------------- */
  .stButton > button {{
    border-radius: 3px; font-weight: 600; font-size: .84rem;
    letter-spacing: .03em; padding: .52rem 1.15rem; border: 1px solid {LINE};
  }}
  .stButton > button[kind="primary"] {{
    background: {ACCENT}; border-color: {ACCENT};
  }}
  div[data-testid="stForm"] {{
    border: 1px solid {LINE}; border-radius: 4px;
    padding: 1.5rem 1.5rem .6rem 1.5rem; background: #fff;
  }}
  label p {{ font-size: .84rem !important; font-weight: 500; }}
</style>
"""


def inject() -> None:
    """Apply the stylesheet. Call once per run, before anything renders."""
    st.markdown(CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Shared fragments
# ---------------------------------------------------------------------------

#: The workflow never changes: FIND -> CHECK -> EXPLAIN -> FIX -> RECHECK.
WORKFLOW = ["Find", "Check", "Explain", "Fix", "Recheck"]


def masthead(meta: str = "") -> None:
    st.markdown(
        f"""<div class="ba-mast">
              <div class="ba-mark">BAAR<span>-</span>AAMAD</div>
              <div class="ba-mast-meta">{meta}</div>
            </div>""",
        unsafe_allow_html=True,
    )


def workflow_strip(active: str | None = None) -> None:
    """Render the five-stage story, optionally highlighting the current one."""
    parts = []
    for index, step in enumerate(WORKFLOW):
        if index:
            parts.append('<span class="ba-arrow">&rarr;</span>')
        now = " is-now" if active and step.lower() == active.lower() else ""
        parts.append(f'<span class="ba-step{now}">{step}</span>')
    st.markdown(f'<div class="ba-flow">{"".join(parts)}</div>', unsafe_allow_html=True)


def section(title: str) -> None:
    st.markdown(f'<div class="ba-h2">{title}</div>', unsafe_allow_html=True)


def kv_table(rows: list[tuple[str, str]]) -> None:
    """Key/value rows. Empty values are shown as 'Not provided', never faked."""
    html = ['<div class="ba-kv">']
    for key, value in rows:
        text = value.strip() if value else ""
        css = "ba-val" if text else "ba-val is-empty"
        html.append(
            f'<div class="ba-row"><div class="ba-key">{key}</div>'
            f'<div class="{css}">{text or "Not provided"}</div></div>'
        )
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def note(text: str, scope: bool = False) -> None:
    cls = "ba-note is-scope" if scope else "ba-note"
    st.markdown(f'<div class="{cls}">{text}</div>', unsafe_allow_html=True)


def disclaimer() -> None:
    """Required on every screen: this is decision support, not authority."""
    st.markdown(
        '<div class="ba-foot">BAAR-AAMAD provides evidence-backed decision '
        "support. Final compliance responsibility remains with the exporter "
        "and the relevant authorities.</div>",
        unsafe_allow_html=True,
    )
