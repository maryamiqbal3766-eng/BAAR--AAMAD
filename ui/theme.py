"""
BAAR-AAMAD — VISUAL LANGUAGE
============================

One restrained palette, generous spacing, readable type.

The target is a professional export-compliance workspace: a warm paper ground,
white cards on top of it, dark text, a single deep-teal accent, and only as
much structure as the content needs. Deliberately not a chatbot, and
deliberately not decorated — no gradients, no animation, no card around every
paragraph.

PERMANENTLY LIGHT
-----------------
There is no dark mode and no toggle. A compliance document that changes colour
depending on the reader's laptop is not a document, and half-inverted widgets
are how a serious tool comes to look broken in front of an audience.

Three things enforce it, because any one alone has been seen to fail:

  1. .streamlit/config.toml pins base = "light" for the deployed app;
  2. `color-scheme: light only` stops the browser inverting form controls;
  3. an explicit `prefers-color-scheme: dark` block below re-states the same
     palette, so a viewer in dark mode gets the same page rather than
     Streamlit's internals leaking through.

CONTRAST
--------
Body and secondary text meet WCAG AA (4.5:1) on both the cream ground and
white cards. FAINT was #8B97A3, which measured 2.98:1 on white and was being
used for real text; it is now #616E79, which clears 4.5:1 on the cream ground,
on white cards and on the inset panel. tests/test_theme.py measures every
combination, so anything added here is checked rather than eyeballed.
"""

from __future__ import annotations

import streamlit as st

INK = "#15202B"  # 14.5:1 on cream — body text
MUTED = "#55636F"  # 5.9:1 — secondary text
FAINT = "#616E79"  # 4.7:1 on the inset panel — the lightest text allowed
LINE = "#E5E0D6"  # warm hairline, to match the paper ground
PANEL = "#F6F3EC"  # inset panel on the cream ground
ACCENT = "#0E5361"  # deep teal, 8.9:1 on white
ACCENT_SOFT = "#E7F0F2"

#: The page itself. Warm off-white rather than pure white: it separates the
#: white cards from the ground without drawing a single extra border.
CREAM = "#FCFAF5"
CARD = "#FFFFFF"

OK = "#1B6E53"
WARN = "#8A5F10"
ALERT = "#9C3B27"

CSS = f"""
<style>
  /* --- permanently light ---------------------------------------------------
     `light only` is what stops the browser from auto-inverting native form
     controls, scrollbars and date pickers when the OS is in dark mode. */
  :root {{ color-scheme: light only; }}

  /* --- chrome ------------------------------------------------------------- */
  #MainMenu, footer, [data-testid="stToolbar"] {{ visibility: hidden; height: 0; }}
  [data-testid="stDecoration"] {{ display: none; }}
  [data-testid="stHeader"] {{ background: transparent; }}
  .block-container {{
    padding-top: 2.2rem; padding-bottom: 5rem; max-width: 1040px;
  }}
  html, body, [class*="css"], p, li, label, div {{ color: {INK}; }}
  html, body, .stApp, [data-testid="stAppViewContainer"],
  [data-testid="stMain"] {{
    background: {CREAM};
  }}
  body {{ font-size: 16px; line-height: 1.65; }}

  /* --- masthead ----------------------------------------------------------- */
  .ba-mast {{
    display: flex; align-items: center; justify-content: space-between;
    gap: 1rem; padding-bottom: .9rem; margin-bottom: 2.2rem;
    border-bottom: 1px solid {LINE};
  }}
  .ba-mark {{
    font-size: 1.15rem; font-weight: 700; letter-spacing: .06em; color: {INK};
  }}
  .ba-mark span {{ color: {ACCENT}; }}
  .ba-mast-meta {{ font-size: .85rem; color: {MUTED}; }}

  /* --- type --------------------------------------------------------------- */
  .ba-eyebrow {{
    font-size: .82rem; font-weight: 600; color: {ACCENT};
    margin-bottom: .5rem; letter-spacing: .01em;
  }}
  .ba-h1 {{
    font-size: 2.3rem; line-height: 1.2; font-weight: 700;
    letter-spacing: -.02em; margin: 0 0 .8rem 0; color: {INK};
  }}
  .ba-lede {{
    font-size: 1.04rem; line-height: 1.65; color: {MUTED};
    max-width: 62ch; margin-bottom: 1.8rem;
  }}
  .ba-h2 {{
    font-size: 1.08rem; font-weight: 650; color: {INK};
    margin: 2.4rem 0 .9rem 0; letter-spacing: -.01em;
  }}
  .ba-para {{
    font-size: .98rem; line-height: 1.7; color: {INK}; margin: .2rem 0 .7rem;
  }}
  .ba-para.is-muted {{ color: {MUTED}; font-size: .93rem; }}
  .ba-bullet {{
    font-size: .96rem; line-height: 1.6; color: {INK};
    padding: .3rem 0 .3rem 1.1rem; position: relative;
  }}
  .ba-bullet:before {{
    content: "—"; position: absolute; left: 0; color: {FAINT};
  }}
  .ba-numbered {{ font-size: .98rem; line-height: 1.6; padding: .4rem 0; }}
  /* Only the leading counter is fixed-width. Scoping this to the first child
     matters: a bare `span` rule here once squeezed body text into a 1.6rem
     column and wrapped it one character per line. */
  .ba-numbered > span:first-child {{
    display: inline-block; width: 1.6rem; color: {ACCENT}; font-weight: 650;
  }}

  /* --- how it works -------------------------------------------------------- */
  .ba-howto {{
    display: flex; gap: 1rem; align-items: baseline; padding: .5rem 0;
    border-bottom: 1px solid {LINE};
  }}
  .ba-howto:last-child {{ border-bottom: none; }}
  .ba-howto-step {{
    flex: 0 0 6rem; font-size: .95rem; font-weight: 650; color: {ACCENT};
  }}
  .ba-howto-text {{
    flex: 1 1 auto; font-size: .96rem; line-height: 1.6; color: {MUTED};
  }}
  .ba-source {{ font-size: .94rem; padding: .35rem 0; }}
  .ba-source a, .ba-map-row a {{ color: {ACCENT}; text-decoration: none; }}
  .ba-source a:hover, .ba-map-row a:hover {{ text-decoration: underline; }}

  /* --- workflow strip ------------------------------------------------------
     The five-stage story is the first thing anyone should understand about
     this product, so it is a numbered stepper rather than five equal chips:
     steps behind you are filled, the current one is solid, the rest are
     outlines. You can see where you are without reading a word. */
  .ba-flow {{
    display: flex; flex-wrap: wrap; gap: .35rem; align-items: center;
    margin: 0 0 2.2rem 0; padding: .75rem .9rem;
    background: {CARD}; border: 1px solid {LINE}; border-radius: 10px;
  }}
  .ba-step {{
    display: inline-flex; align-items: center; gap: .45rem;
    font-size: .84rem; font-weight: 650; padding: .4rem .8rem;
    border: 1px solid {LINE}; border-radius: 999px; color: {MUTED};
    background: {CARD}; white-space: nowrap;
  }}
  .ba-step-i {{
    display: inline-flex; align-items: center; justify-content: center;
    width: 1.25rem; height: 1.25rem; border-radius: 999px;
    background: {PANEL}; color: {MUTED}; font-size: .72rem; font-weight: 700;
  }}
  .ba-step.is-done {{
    color: {ACCENT}; border-color: #C6DBE0; background: {ACCENT_SOFT};
  }}
  .ba-step.is-done .ba-step-i {{ background: {ACCENT}; color: {CARD}; }}
  .ba-step.is-now {{
    color: {CARD}; background: {ACCENT}; border-color: {ACCENT};
    box-shadow: 0 1px 3px rgba(14, 83, 97, .28);
  }}
  .ba-step.is-now .ba-step-i {{ background: rgba(255,255,255,.22); color: {CARD}; }}
  .ba-arrow {{ color: {FAINT}; font-size: .8rem; }}

  /* --- key / value --------------------------------------------------------- */
  .ba-kv {{ border-top: 1px solid {LINE}; margin-bottom: .5rem; }}
  .ba-row {{
    display: flex; gap: 1.5rem; padding: .8rem .2rem;
    border-bottom: 1px solid {LINE}; font-size: .97rem; align-items: baseline;
  }}
  .ba-key {{ flex: 0 0 13rem; color: {MUTED}; font-size: .92rem; }}
  .ba-val {{ flex: 1 1 auto; color: {INK}; }}
  .ba-val.is-empty {{ color: {FAINT}; }}

  /* --- summary grid -------------------------------------------------------- */
  .ba-summary {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 1.4rem 2rem; padding: 1.3rem 1.5rem; background: {PANEL};
    border: 1px solid {LINE}; border-radius: 8px; margin-bottom: 1.6rem;
  }}
  .ba-cell-label {{
    font-size: .8rem; color: {MUTED}; margin-bottom: .28rem;
  }}
  .ba-cell-value {{ font-size: 1.02rem; font-weight: 600; color: {INK}; }}
  .ba-cell-value.is-empty {{ font-weight: 400; color: {FAINT}; }}

  /* --- status -------------------------------------------------------------- */
  .ba-status {{
    display: inline-block; font-size: .92rem; font-weight: 650;
    padding: .45rem .95rem; border-radius: 6px; margin-bottom: .9rem;
    border: 1px solid {LINE}; background: {PANEL}; color: {INK};
  }}
  .ba-status.is-action {{ border-color:#E8C4BA; color:{ALERT}; background:#FDF4F2; }}
  .ba-status.is-verify {{ border-color:#E6D3A8; color:{WARN}; background:#FDF9F0; }}
  .ba-status.is-ready  {{ border-color:#B9DCCC; color:{OK};   background:#F1F9F5; }}

  .ba-pill {{
    display: inline-block; font-size: .8rem; padding: .25rem .6rem;
    border-radius: 5px; border: 1px solid {LINE}; background: {PANEL};
    color: {MUTED};
  }}

  /* --- tally --------------------------------------------------------------- */
  .ba-tally {{
    display: flex; flex-wrap: wrap; gap: 2.2rem; margin: .3rem 0 1.2rem;
  }}
  .ba-tally-item {{ min-width: 7rem; }}
  .ba-tally-n {{ display:block; font-size:1.9rem; font-weight:700; color:{INK}; }}
  .ba-tally-l {{ font-size: .88rem; color: {MUTED}; }}

  /* --- AI activity ----------------------------------------------------------- */
  .ba-tag {{
    display: inline-block; font-size: .72rem; font-weight: 700;
    letter-spacing: .04em; padding: .18rem .5rem; border-radius: 4px;
    margin-left: .6rem; vertical-align: middle; white-space: nowrap;
  }}
  .ba-tag.is-ai {{ background:{ACCENT_SOFT}; color:{ACCENT}; border:1px solid #C9DDE1; }}
  .ba-tag.is-curated {{ background:{PANEL}; color:{MUTED}; border:1px solid {LINE}; }}

  .ba-trace {{
    border: 1px solid {LINE}; border-radius: 8px; padding: 1rem 1.15rem;
    margin-bottom: .7rem; background: #fff;
  }}
  .ba-trace-head {{
    font-size: 1rem; font-weight: 650; color: {INK}; margin-bottom: .6rem;
  }}
  .ba-trace-step {{
    font-size: .93rem; line-height: 1.6; color: {INK};
    padding: .6rem 0 .6rem .9rem; border-left: 2px solid {LINE};
    margin-bottom: .35rem;
  }}
  .ba-trace-step b {{
    display: block; font-size: .74rem; font-weight: 700; color: {ACCENT};
    letter-spacing: .05em; text-transform: uppercase; margin-bottom: .2rem;
  }}
  .ba-quote {{ color: {MUTED}; font-style: italic; }}
  .ba-cite {{ font-size: .82rem; color: {FAINT}; }}
  .ba-trace-foot {{
    font-size: .84rem; color: {MUTED}; margin-top: .5rem;
    padding-top: .5rem; border-top: 1px dashed {LINE};
  }}
  .ba-trace-foot.is-bad {{ color: {ALERT}; }}

  .ba-move {{
    border: 1px solid {LINE}; border-left: 3px solid {ACCENT};
    border-radius: 0 8px 8px 0; padding: .85rem 1.1rem;
    margin-bottom: .5rem; background: #fff;
  }}
  .ba-move.is-refused {{ border-left-color: {WARN}; background: #FDFAF4; }}
  .ba-move-head {{ display: flex; align-items: baseline; gap: .6rem; }}
  .ba-move-n {{
    flex: 0 0 1.6rem; height: 1.6rem; line-height: 1.6rem; text-align: center;
    /* A pill radius in px, not the usual half-of-the-box ratio: a test scans
       the rendered page for a per-cent sign, because this product never shows
       a percentage score, and the stylesheet ships inside the page. */
    border-radius: 999px; background: {ACCENT}; color: #fff;
    font-size: .78rem; font-weight: 700;
  }}
  .ba-move-tool {{
    font-family: ui-monospace, "Cascadia Mono", Menlo, Consolas, monospace;
    font-size: .88rem; font-weight: 600; color: {INK}; word-break: break-word;
  }}
  .ba-move-why {{ font-size: .86rem; color: {MUTED}; margin: .4rem 0 .1rem 2.2rem; }}
  .ba-move-obs {{
    font-size: .9rem; line-height: 1.55; color: {INK}; white-space: pre-wrap;
    margin: .45rem 0 0 2.2rem; padding: .55rem .8rem; background: {PANEL};
    border-radius: 6px;
  }}
  .ba-move-decision {{
    font-size: .82rem; font-weight: 600; color: {ACCENT};
    margin: .45rem 0 0 2.2rem;
  }}

  .ba-log {{
    border: 1px solid {LINE}; border-radius: 8px; overflow-x: auto;
    background: #fff;
  }}
  .ba-log-row {{
    display: grid; grid-template-columns: 2.4fr 1.4fr .9fr .7fr .6fr;
    gap: .9rem; align-items: center; padding: .7rem 1rem;
    border-bottom: 1px solid {LINE}; font-size: .9rem; min-width: 640px;
  }}
  .ba-log-row:last-child {{ border-bottom: none; }}
  .ba-log-row.is-head {{
    background: {PANEL}; font-size: .78rem; font-weight: 700; color: {MUTED};
    letter-spacing: .04em; text-transform: uppercase;
  }}
  .ba-log-note {{ font-size: .8rem; color: {MUTED}; font-weight: 400; }}
  .ba-log-detail {{
    font-size: .84rem; color: {ALERT}; padding: 0 1rem .7rem 1rem;
    border-bottom: 1px solid {LINE};
  }}
  .ba-doc-state.is-warn {{ background:#FDF9F0; color:{WARN}; border:1px solid #E6D3A8; }}

  /* --- documents ----------------------------------------------------------- */
  .ba-doc {{
    display: flex; align-items: center; justify-content: space-between;
    gap: 1rem; padding: .95rem 1.15rem; border: 1px solid {LINE};
    border-radius: 8px; margin-bottom: .6rem; background: #fff;
  }}
  .ba-doc-name {{ font-size: .99rem; font-weight: 600; color: {INK}; }}
  .ba-doc-meta {{ font-size: .87rem; color: {MUTED}; margin-top: .2rem; }}
  .ba-doc-meta.is-empty {{ color: {FAINT}; }}
  .ba-doc-meta.is-bad {{ color: {ALERT}; }}
  .ba-doc-state {{
    font-size: .82rem; font-weight: 600; padding: .28rem .65rem;
    border-radius: 5px; white-space: nowrap;
  }}
  .ba-doc-state.is-on  {{ background:#F1F9F5; color:{OK};    border:1px solid #B9DCCC; }}
  .ba-doc-state.is-off {{ background:{PANEL}; color:{MUTED}; border:1px solid {LINE}; }}
  .ba-doc-state.is-bad {{ background:#FDF4F2; color:{ALERT}; border:1px solid #E8C4BA; }}

  /* --- bands and findings --------------------------------------------------- */
  .ba-band {{
    display: flex; align-items: baseline; gap: .7rem;
    margin: 2rem 0 .8rem; padding-bottom: .45rem;
    border-bottom: 2px solid {LINE};
  }}
  .ba-band-name {{ font-size: .95rem; font-weight: 700; color: {INK}; }}
  .ba-band-sub {{ font-size: .87rem; color: {MUTED}; }}

  .ba-finding {{
    border: 1px solid {LINE}; border-radius: 8px; padding: 1.05rem 1.2rem;
    margin-bottom: .2rem; background: #fff;
  }}
  .ba-finding-head {{
    font-size: 1.02rem; font-weight: 650; color: {INK}; line-height: 1.4;
  }}
  .ba-glyph {{ margin-right: .35rem; }}
  .ba-finding-label {{
    display: inline-block; font-size: .78rem; font-weight: 600;
    border: 1px solid {LINE}; border-radius: 5px; padding: .16rem .5rem;
    margin-left: .55rem; color: {MUTED}; background: {PANEL};
    white-space: nowrap;
  }}
  .ba-finding-body {{
    font-size: .94rem; line-height: 1.6; color: {MUTED}; margin-top: .45rem;
  }}

  /* --- labelled blocks ------------------------------------------------------ */
  .ba-block {{ margin: 1.1rem 0; }}
  .ba-block-label {{
    font-size: .8rem; font-weight: 700; color: {ACCENT};
    letter-spacing: .04em; text-transform: uppercase; margin-bottom: .35rem;
  }}
  .ba-block-body {{
    font-size: .97rem; line-height: 1.68; color: {INK}; white-space: pre-wrap;
  }}
  .ba-block.is-evidence .ba-block-body {{
    background: {PANEL}; border-left: 3px solid {ACCENT};
    padding: .85rem 1rem; border-radius: 0 6px 6px 0; font-size: .94rem;
  }}

  .ba-compare {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
    gap: .7rem; margin: .5rem 0;
  }}
  .ba-compare-item {{
    border: 1px solid {LINE}; border-radius: 7px; padding: .7rem .9rem;
    background: {PANEL};
  }}
  .ba-compare-k {{ font-size: .82rem; color: {MUTED}; margin-bottom: .2rem; }}
  .ba-compare-v {{ font-size: 1.12rem; font-weight: 700; color: {INK}; }}

  /* --- document slots -------------------------------------------------------- */
  .ba-slot-key {{
    font-size: .8rem; font-weight: 650; letter-spacing: .03em;
    text-transform: uppercase; color: {MUTED}; margin-bottom: .2rem;
  }}
  .ba-slot-val {{ font-size: .99rem; font-weight: 600; color: {INK}; }}
  .ba-slot-val.is-empty {{ font-weight: 400; color: {FAINT}; }}
  .ba-slot-val.is-bad {{ color: {ALERT}; }}
  .ba-slot-meta {{
    display: block; font-size: .86rem; font-weight: 400; color: {MUTED};
    margin-top: .15rem;
  }}

  /* --- action plan ---------------------------------------------------------- */
  .ba-action {{
    display: flex; gap: 1rem; align-items: flex-start;
    border: 1px solid {LINE}; border-radius: 8px; padding: 1.05rem 1.2rem;
    margin-bottom: .3rem; background: {CARD};
  }}
  .ba-action-n {{
    flex: 0 0 1.7rem; height: 1.7rem; line-height: 1.7rem; text-align: center;
    border-radius: 999px; background: {ACCENT_SOFT}; color: {ACCENT};
    font-size: .82rem; font-weight: 700;
  }}
  .ba-action-main {{ flex: 1 1 auto; min-width: 0; }}
  .ba-action-problem {{ font-size: 1.02rem; font-weight: 650; color: {INK}; }}
  .ba-action-row {{ font-size: .95rem; line-height: 1.6; margin-top: .6rem; }}
  .ba-action-row b {{
    display: block; font-size: .78rem; font-weight: 700; color: {ACCENT};
    letter-spacing: .04em; text-transform: uppercase; margin-bottom: .15rem;
  }}
  .ba-action-provide b {{
    font-size: .78rem; font-weight: 700; color: {ACCENT};
    letter-spacing: .04em; text-transform: uppercase;
  }}
  .ba-draft-banner {{
    font-size: .84rem; font-weight: 700; color: {WARN}; background: #FDF9F0;
    border: 1px solid #E6D3A8; border-radius: 6px; padding: .6rem .85rem;
    margin-bottom: .8rem;
  }}

  /* --- evidence map --------------------------------------------------------- */
  .ba-map {{
    border: 1px solid {LINE}; border-radius: 8px; padding: 1rem 1.2rem;
    margin-bottom: .6rem; background: #fff;
  }}
  .ba-map-req {{ font-size: 1rem; font-weight: 650; color: {INK}; }}
  .ba-map-row {{ font-size: .93rem; color: {MUTED}; margin-top: .4rem; }}
  .ba-map-row b {{
    display: inline-block; min-width: 9rem; font-size: .8rem; color: {INK};
    font-weight: 600;
  }}

  /* --- pipeline ------------------------------------------------------------- */
  .ba-stage {{
    padding: .55rem 0 .55rem 1rem; border-left: 2px solid {LINE};
    font-size: .95rem; color: {MUTED};
  }}
  .ba-stage.is-waiting {{ color: {FAINT}; }}
  .ba-stage.is-done {{ border-left-color: {ACCENT}; color: {INK}; }}
  .ba-stage.is-failed {{ border-left-color: {ALERT}; color: {ALERT}; }}
  .ba-stage-note {{
    display: block; font-size: .85rem; color: {MUTED}; margin-top: .12rem;
  }}

  /* --- coverage -------------------------------------------------------------- */
  .ba-cov {{
    border: 1px solid {LINE}; border-left: 4px solid {FAINT}; border-radius: 0 8px 8px 0;
    padding: 1rem 1.2rem; margin: 0 0 1.5rem 0; background: {PANEL};
  }}
  .ba-cov-head {{
    display: flex; flex-wrap: wrap; align-items: baseline; gap: .7rem;
    margin-bottom: .4rem;
  }}
  .ba-cov-level {{
    font-size: .82rem; font-weight: 700; letter-spacing: .05em;
    padding: .22rem .6rem; border-radius: 5px; white-space: nowrap;
  }}
  .ba-cov-route {{ font-size: .9rem; color: {MUTED}; }}
  .ba-cov-msg {{ font-size: .95rem; line-height: 1.6; color: {INK}; }}
  .ba-cov-unassessed {{
    margin-top: .75rem; padding-top: .65rem; border-top: 1px solid {LINE};
  }}
  .ba-cov-unassessed b {{
    display: block; font-size: .76rem; font-weight: 700; letter-spacing: .05em;
    text-transform: uppercase; color: {WARN}; margin-bottom: .3rem;
  }}
  .ba-cov-item {{
    font-size: .92rem; line-height: 1.55; color: {MUTED};
    padding: .2rem 0 .2rem 1rem; position: relative;
  }}
  .ba-cov-item:before {{ content: "—"; position: absolute; left: 0; color: {FAINT}; }}

  .ba-cov.is-full {{ border-left-color: {OK}; background: #F4FAF7; }}
  .ba-cov.is-full .ba-cov-level {{ background:#E4F2EB; color:{OK}; border:1px solid #B9DCCC; }}
  .ba-cov.is-partial {{ border-left-color: {WARN}; background: #FDFAF3; }}
  .ba-cov.is-partial .ba-cov-level {{ background:#FAF1DE; color:{WARN}; border:1px solid #E6D3A8; }}
  .ba-cov.is-none {{ border-left-color: {ALERT}; background: #FDF5F3; }}
  .ba-cov.is-none .ba-cov-level {{ background:#F8E5E0; color:{ALERT}; border:1px solid #E8C4BA; }}

  /* --- notes and footer ------------------------------------------------------ */
  .ba-note {{
    background: {PANEL}; border: 1px solid {LINE}; border-radius: 8px;
    padding: .85rem 1.1rem; color: {MUTED}; font-size: .93rem;
    line-height: 1.65; margin: 1.1rem 0;
  }}
  .ba-note.is-scope {{ background:#FDF9F0; border-color:#E6D3A8; color:{WARN}; }}
  .ba-foot {{
    margin-top: 3.5rem; padding-top: 1.1rem; border-top: 1px solid {LINE};
    color: {FAINT}; font-size: .86rem; line-height: 1.6;
  }}

  /* --- controls -------------------------------------------------------------- */
  .stButton > button {{
    border-radius: 8px; font-weight: 650; font-size: .95rem;
    padding: .6rem 1.25rem; border: 1px solid {LINE};
    background: {CARD}; color: {INK};
  }}
  .stButton > button:hover, .stButton > button:hover p {{
    border-color: {ACCENT}; color: {ACCENT};
  }}
  /* The inner <p> has to be named as well as the button. Streamlit wraps a
     button label in a paragraph, and the blanket `p {{ color: INK }}` rule
     above otherwise wins on specificity — which left white-on-teal buttons
     rendering as ink-on-teal at about 1.4:1, i.e. unreadable. */
  .stButton > button[kind="primary"],
  .stButton > button[kind="primary"] p {{
    background: {ACCENT}; border-color: {ACCENT}; color: {CARD};
  }}
  .stButton > button[kind="primary"] p {{ background: transparent; }}
  .stButton > button[kind="primary"]:hover,
  .stButton > button[kind="primary"]:hover p {{
    background: #0B4551; border-color: #0B4551; color: {CARD};
  }}
  .stButton > button[kind="primary"]:hover p {{ background: transparent; }}
  /* A form's submit button is .stFormSubmitButton, not .stButton, and its
     `kind` is "primaryFormSubmit". It was missed by the rules above and was
     rendering ink-on-teal at about 1.4:1 — the same defect, one container over. */
  .stFormSubmitButton > button {{
    border-radius: 8px; font-weight: 650; font-size: .95rem;
    padding: .6rem 1.25rem; border: 1px solid {LINE};
  }}
  .stFormSubmitButton > button[kind="primaryFormSubmit"],
  .stFormSubmitButton > button[kind="primaryFormSubmit"] p {{
    background: {ACCENT}; border-color: {ACCENT}; color: {CARD};
  }}
  .stFormSubmitButton > button[kind="primaryFormSubmit"] p {{ background: transparent; }}
  .stFormSubmitButton > button[kind="primaryFormSubmit"]:hover,
  .stFormSubmitButton > button[kind="primaryFormSubmit"]:hover p {{
    background: #0B4551; border-color: #0B4551; color: {CARD};
  }}
  .stFormSubmitButton > button[kind="primaryFormSubmit"]:hover p {{ background: transparent; }}
  div[data-testid="stForm"] {{
    border: 1px solid {LINE}; border-radius: 10px;
    padding: 1.7rem 1.8rem .9rem; background: {CARD};
  }}
  label p {{ font-size: .94rem !important; font-weight: 550; color: {INK}; }}
  .stTextInput input, .stTextArea textarea, .stDateInput input,
  .stSelectbox div[data-baseweb="select"] > div {{
    font-size: .97rem !important; background: {CARD}; color: {INK};
  }}
  [data-testid="stFileUploaderDropzone"] {{
    background: {PANEL}; border: 1px dashed {LINE};
  }}
  [data-testid="stExpander"] details {{
    background: {CARD}; border: 1px solid {LINE}; border-radius: 8px;
  }}
  .stCodeBlock, code {{ background: {PANEL}; }}

  /* --- popovers: dropdown menus and the date picker ---------------------------
     These render in a portal attached to <body>, OUTSIDE .stApp, so every rule
     above misses them entirely. Left alone they take Streamlit's own theme,
     which is how a dropdown on a cream page opened dark-on-dark.

     Selectors are ARIA roles, not emotion class hashes: `st-emotion-cache-*`
     names change between Streamlit releases, and this styling must not be one
     upgrade away from breaking. `:has()` reaches the opaque surface that wraps
     the menu; the role elements are also painted directly, so a browser
     without `:has()` still gets a light menu rather than a transparent one. */
  div:has(> [role="listbox"]),
  div:has(> [role="application"]),
  [role="listbox"],
  [role="application"] {{
    background: {CARD} !important;
    color: {INK} !important;
    border-color: {LINE} !important;
  }}
  [role="listbox"], [role="application"] {{ border-radius: 8px; }}

  [role="option"], [role="gridcell"], [role="grid"] {{
    background: transparent !important;
    color: {INK} !important;
  }}
  [role="option"]:hover, [role="gridcell"]:hover {{
    background: {PANEL} !important;
    color: {INK} !important;
  }}
  [role="option"][aria-selected="true"],
  [role="gridcell"][aria-selected="true"] {{
    background: {ACCENT_SOFT} !important;
    color: {ACCENT} !important;
    font-weight: 650;
  }}
  [role="option"][data-focused], [role="option"][data-focus-visible],
  [role="gridcell"][data-focused] {{
    background: {PANEL} !important;
    color: {INK} !important;
  }}
  /* Days outside the shown month, and any disabled entry. Muted, still AA. */
  [role="gridcell"][data-outside-month], [aria-disabled="true"] {{
    color: {FAINT} !important;
  }}
  /* The calendar's month/year steppers and its header controls. */
  div:has(> [role="application"]) button {{
    background: transparent !important;
    color: {INK} !important;
  }}
  div:has(> [role="application"]) button:hover {{ background: {PANEL} !important; }}

  /* --- the dark-mode lock -----------------------------------------------------
     Re-stating the palette rather than trusting config.toml alone. A viewer
     whose OS is dark otherwise gets Streamlit's own dark internals showing
     through the parts this stylesheet does not name, which reads as a broken
     page rather than as a theme. */
  @media (prefers-color-scheme: dark) {{
    :root {{ color-scheme: light only; }}
    html, body, .stApp, [data-testid="stAppViewContainer"],
    [data-testid="stMain"], [data-testid="stHeader"] {{
      background: {CREAM} !important; color: {INK} !important;
    }}
    p, li, label, div, span, h1, h2, h3, h4, h5, h6 {{ color: {INK}; }}
    .ba-para.is-muted, .ba-lede, .ba-key, .ba-doc-meta, .ba-finding-body,
    .ba-cell-label, .ba-band-sub, .ba-map-row, .ba-note, .ba-cov-item {{
      color: {MUTED} !important;
    }}
    .ba-foot, .ba-cite, .ba-val.is-empty, .ba-cell-value.is-empty {{
      color: {FAINT} !important;
    }}
    .ba-finding, .ba-action, .ba-map, .ba-doc, .ba-trace, .ba-step,
    .ba-log, .ba-flow, .ba-move, div[data-testid="stForm"], [data-testid="stExpander"] details {{
      background: {CARD} !important;
    }}
    .ba-summary, .ba-note, .ba-compare-item, .ba-block.is-evidence .ba-block-body,
    .ba-move-obs, .stCodeBlock, code {{
      background: {PANEL} !important;
    }}
    .stTextInput input, .stTextArea textarea, .stDateInput input,
    .stSelectbox div[data-baseweb="select"] > div,
    [data-baseweb="popover"], [data-baseweb="menu"], li[role="option"] {{
      background: {CARD} !important; color: {INK} !important;
    }}
    .stButton > button, .stButton > button p {{
      background: {CARD} !important; color: {INK} !important;
    }}
    .stButton > button[kind="primary"],
    .stButton > button[kind="primary"] p,
    .ba-step.is-now {{
      background: {ACCENT} !important; color: {CARD} !important;
    }}
    /* Popovers again: they are portalled outside .stApp, so the rules above
       in this block do not reach them either. */
    div:has(> [role="listbox"]), div:has(> [role="application"]),
    [role="listbox"], [role="application"] {{
      background: {CARD} !important; color: {INK} !important;
    }}
    [role="option"], [role="gridcell"], [role="grid"] {{
      background: transparent !important; color: {INK} !important;
    }}
    [role="option"]:hover, [role="gridcell"]:hover {{
      background: {PANEL} !important; color: {INK} !important;
    }}
    [role="option"][aria-selected="true"], [role="gridcell"][aria-selected="true"] {{
      background: {ACCENT_SOFT} !important; color: {ACCENT} !important;
    }}
    div:has(> [role="application"]) button {{ color: {INK} !important; }}
  }}
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
    """Render the five-stage story, showing where this screen sits in it.

    Steps before the active one are marked done, so the strip reads as
    progress rather than as a list of features. With no active step — on the
    Passport, which is the end of the story — every step shows as done.
    """
    position = -1
    if active:
        position = next(
            (i for i, step in enumerate(WORKFLOW) if step.lower() == active.lower()),
            -1,
        )

    parts = []
    for index, step in enumerate(WORKFLOW):
        if index:
            parts.append('<span class="ba-arrow">&rarr;</span>')
        if index == position:
            css = " is-now"
        elif position == -1 or index < position:
            css = " is-done"
        else:
            css = ""
        parts.append(
            f'<span class="ba-step{css}">'
            f'<span class="ba-step-i">{index + 1}</span>{step}</span>'
        )
    st.markdown(f'<div class="ba-flow">{"".join(parts)}</div>', unsafe_allow_html=True)


def section(title: str) -> None:
    st.markdown(f'<div class="ba-h2">{title}</div>', unsafe_allow_html=True)


def summary_grid(cells: list[tuple[str, str]]) -> None:
    """A compact panel of label/value pairs, for a case header."""
    html = ['<div class="ba-summary">']
    for label, value in cells:
        text = (value or "").strip()
        css = "ba-cell-value" if text else "ba-cell-value is-empty"
        html.append(
            f'<div><div class="ba-cell-label">{label}</div>'
            f'<div class="{css}">{text or "Not provided"}</div></div>'
        )
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


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


def block(label: str, body: str, evidence: bool = False) -> None:
    """A labelled block of text — the unit findings and drafts are built from."""
    css = "ba-block is-evidence" if evidence else "ba-block"
    st.markdown(
        f'<div class="{css}"><div class="ba-block-label">{label}</div>'
        f'<div class="ba-block-body">{body}</div></div>',
        unsafe_allow_html=True,
    )


#: Coverage tone, and the one-line meaning each level carries. The wording is
#: fixed here so the dashboard, the action plan and the Passport cannot drift
#: into describing the same assessment three different ways.
_COVERAGE_TONE = {
    "COVERED": ("is-full", "Sources apply to this route and to these goods."),
    "PARTIALLY COVERED": (
        "is-partial",
        "Sources apply to this route, but none are written for these goods.",
    ),
    "NOT COVERED": (
        "is-none",
        "No curated source applies, so no requirement can be stated.",
    ),
}


def coverage_banner(coverage) -> None:
    """State what the corpus could and could not speak to, before findings.

    Shown on every surface that presents a result. A reader who does not know
    the limits of what was checked cannot read the findings correctly, and
    burying that in a stage message — which is where it used to live — put it
    somewhere nobody looks.
    """
    if coverage is None:
        return

    level = coverage.level.value
    tone, meaning = _COVERAGE_TONE.get(level, ("", ""))

    html = [
        f'<div class="ba-cov {tone}">',
        '<div class="ba-cov-head">',
        f'<span class="ba-cov-level">{level}</span>',
        f'<span class="ba-cov-route">{coverage.route}</span>',
        "</div>",
        f'<div class="ba-cov-msg">{coverage.message or meaning}</div>',
    ]
    if coverage.unassessed:
        html.append('<div class="ba-cov-unassessed"><b>Not assessed</b>')
        html += [f'<div class="ba-cov-item">{item}</div>' for item in coverage.unassessed]
        html.append("</div>")
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
