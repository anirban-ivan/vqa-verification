"""
QA Verification tool — Bengali Infographic VLM Benchmark.

Reviewers page through each infographic image, check its generated QA
pairs against the image, and approve / reject / correct each one.
Progress is stored in `storage` (Supabase when deployed, local SQLite
when run locally) so all reviewers see the same live state.

Scope for this run is controlled by CSV_PATH / IMAGES_DIR / PILOT_IMAGES
below — set PILOT_IMAGES to None to review every row in CSV_PATH.
"""

from collections import Counter
from pathlib import Path

import pandas as pd
import streamlit as st

from storage import get_storage

# ── Config ────────────────────────────────────────────────────────────────
CSV_PATH = Path(r"E:\Downloads\bengali chart qa\New folder\images_png\PA\final_batch.csv")
IMAGES_DIR = Path(r"E:\Downloads\bengali chart qa\New folder\images_png\PA")
PILOT_IMAGES = None  # None = review the whole CSV

REVIEWERS = ["Anirban", "Ayman", "Mahir"]  # swap in real names before sharing

TYPE_LABELS = {
    "lookup": "Lookup",
    "multi_step_lookup": "Multi-step Lookup",
    "multi-step_lookup": "Multi-step Lookup",
    "multi-step lookup": "Multi-step Lookup",
    "multistep_lookup": "Multi-step Lookup",
    "reasoning": "Reasoning",
    "unanswerable": "Unanswerable",
    "mcq": "MCQ",
}

STATUS_STYLE = {
    "unverified": ("#6b7280", "#f3f4f6"),
    "approved":   ("#15803d", "#dcfce7"),
    "rejected":   ("#b91c1c", "#fee2e2"),
}

st.set_page_config(page_title="QA Verification", layout="wide")

st.markdown("""
<style>
.badge { display: inline-block; padding: 2px 10px; border-radius: 999px;
         font-size: 12px; font-weight: 600; margin-right: 6px; }
.bn { font-size: 17px; line-height: 1.6; }
.label { font-size: 11px; text-transform: uppercase; letter-spacing: .04em;
         color: #6b7280; margin-bottom: 2px; }
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def get_cached_storage():
    """Create the storage client once per server process instead of on every
    rerun — a fresh Supabase client per interaction adds real round-trip
    latency (each click causes at least one script rerun)."""
    return get_storage()


storage = get_cached_storage()


@st.cache_data
def load_qa(csv_path: str, pilot_images: tuple | None) -> pd.DataFrame:
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    if pilot_images:
        df = df[df["image_filename"].isin(pilot_images)]
    df["key"] = df["image_filename"] + "::" + df["pair_id"].astype(str)
    return df.reset_index(drop=True)


def badge(text: str, fg: str, bg: str) -> str:
    return f'<span class="badge" style="color:{fg};background:{bg}">{text}</span>'


qa_df = load_qa(str(CSV_PATH), tuple(PILOT_IMAGES) if PILOT_IMAGES else None)
verified = storage.get_all()
images = qa_df["image_filename"].unique().tolist()

# ── Sidebar: reviewer + navigation ──────────────────────────────────────────
if "pair_idx" not in st.session_state:
    st.session_state.pair_idx = 0
st.session_state.pair_idx = max(0, min(st.session_state.pair_idx, len(qa_df) - 1))

with st.sidebar:
    st.markdown("### QA Verification")
    reviewer = st.selectbox("Reviewing as", REVIEWERS)
    page = st.radio("View", ["Review", "Data"], label_visibility="collapsed")

    st.markdown("---")
    st.markdown("**By reviewer**")
    reviewer_counts = Counter(
        v.get("reviewer") for v in verified.values() if v.get("status", "unverified") != "unverified"
    )
    for name in REVIEWERS:
        st.markdown(f"- {name} &nbsp; `{reviewer_counts.get(name, 0)}`", unsafe_allow_html=True)
    other = sum(c for n, c in reviewer_counts.items() if n not in REVIEWERS)
    if other:
        st.markdown(f"- Other &nbsp; `{other}`", unsafe_allow_html=True)

    if page == "Review":
        st.markdown("---")
        st.markdown("**Images**")
        for img in images:
            pairs = qa_df[qa_df["image_filename"] == img]
            done = sum(1 for _, p in pairs.iterrows()
                       if verified.get(p["key"], {}).get("status", "unverified") != "unverified")
            first_idx = pairs.index[0]
            if st.button(f"{img}  ·  {done}/{len(pairs)}", key=f"jump_{img}", use_container_width=True):
                st.session_state.pair_idx = first_idx
                st.rerun()

total_pairs = len(qa_df)
total_done = sum(1 for k in qa_df["key"] if verified.get(k, {}).get("status", "unverified") != "unverified")


def goto(new_idx: int) -> None:
    st.session_state.pair_idx = new_idx
    st.rerun()


# ── Review page — one question at a time; the image stays pinned while its
# own questions are being stepped through, since Next only changes it once
# that image's pairs are exhausted (they're grouped together in qa_df). ──────
if page == "Review":
    st.progress(total_done / total_pairs if total_pairs else 0,
                text=f"{total_done} of {total_pairs} pairs verified")

    idx = st.session_state.pair_idx
    row = qa_df.iloc[idx]
    key = row["key"]
    current_img = row["image_filename"]

    nav_l, nav_mid, nav_r = st.columns([1, 4, 1])
    with nav_l:
        if st.button("Previous", use_container_width=True, disabled=idx == 0):
            goto(idx - 1)
    with nav_mid:
        st.markdown(f"<div style='text-align:center'>Question {idx + 1} of {total_pairs}</div>",
                    unsafe_allow_html=True)
    with nav_r:
        if st.button("Next", use_container_width=True, disabled=idx == total_pairs - 1):
            goto(idx + 1)

    img_col, qa_col = st.columns([5, 6], gap="large")

    with img_col:
        st.image(str(IMAGES_DIR / current_img), use_container_width=True, caption=current_img)

    with qa_col:
        state = verified.get(key, {})
        status = state.get("status", "unverified")
        fg, bg = STATUS_STYLE[status]
        type_label = TYPE_LABELS.get(row["question_type"], row["question_type"])

        with st.container(border=True):
            header = badge(type_label, "#3730a3", "#e0e7ff") + badge(status.capitalize(), fg, bg)
            st.markdown(header, unsafe_allow_html=True)

            st.markdown(f'<div class="label">Question</div><div class="bn">{row["question_bn"]}</div>',
                        unsafe_allow_html=True)
            st.markdown(f'<div class="label" style="margin-top:8px">Answer</div>'
                        f'<div class="bn"><b>{row["answer_bn"]}</b></div>', unsafe_allow_html=True)

            is_last = idx == total_pairs - 1
            btn_a, btn_r, btn_spacer = st.columns([1, 1, 3])
            with btn_a:
                if st.button("Approve", key=f"approve_{key}", use_container_width=True):
                    storage.upsert(key, {
                        "image_filename": row["image_filename"], "pair_id": row["pair_id"],
                        "status": "approved", "correction_bn": state.get("correction_bn", ""),
                        "reviewer": reviewer,
                    })
                    goto(idx if is_last else idx + 1)
            with btn_r:
                if st.button("Reject", key=f"reject_{key}", use_container_width=True):
                    storage.upsert(key, {
                        "image_filename": row["image_filename"], "pair_id": row["pair_id"],
                        "status": "rejected", "correction_bn": state.get("correction_bn", ""),
                        "reviewer": reviewer,
                    })
                    goto(idx if is_last else idx + 1)

            with st.expander("Suggest a correction"):
                correction = st.text_area("Corrected answer (Bengali)", value=state.get("correction_bn", ""),
                                           key=f"correction_{key}", label_visibility="collapsed")
                if st.button("Save correction", key=f"save_{key}"):
                    storage.upsert(key, {
                        "image_filename": row["image_filename"], "pair_id": row["pair_id"],
                        "status": status, "correction_bn": correction, "reviewer": reviewer,
                    })
                    st.rerun()

# ── Data page ────────────────────────────────────────────────────────────────
else:
    st.markdown("### All verification data")
    merged = qa_df.copy()
    merged["status"] = merged["key"].map(lambda k: verified.get(k, {}).get("status", "unverified"))
    merged["correction_bn"] = merged["key"].map(lambda k: verified.get(k, {}).get("correction_bn", ""))
    merged["verified_by"] = merged["key"].map(lambda k: verified.get(k, {}).get("reviewer", ""))
    merged["updated_at"] = merged["key"].map(lambda k: verified.get(k, {}).get("updated_at", ""))

    status_filter = st.multiselect("Filter by status", ["unverified", "approved", "rejected"],
                                    default=["unverified", "approved", "rejected"])
    view = merged[merged["status"].isin(status_filter)]

    display_cols = ["image_filename", "pair_id", "question_type", "question_bn", "answer_bn",
                     "status", "correction_bn", "verified_by", "updated_at"]
    st.dataframe(view[display_cols], use_container_width=True, height=500)

    st.download_button(
        "Export current state as CSV",
        data=view[display_cols].to_csv(index=False).encode("utf-8-sig"),
        file_name="verification_export.csv",
        mime="text/csv",
    )
