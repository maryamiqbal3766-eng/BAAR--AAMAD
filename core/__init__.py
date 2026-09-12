"""BAAR-AAMAD core: shared contract, rules, failures and the Groq gateway.

Nothing in `core` may import from `modules` or `ui`. The dependency arrow
points one way only:

    ui  ->  modules  ->  core

This keeps every team module testable in isolation (and in Colab) without
pulling in Streamlit.
"""
