"""MediaMind UI: Instagram-style gallery + a search bar for the agent + an approvals queue.
Talks to the FastAPI service only (API_URL). Run: streamlit run ui/app.py
"""
import os

import requests
import streamlit as st

API = os.environ.get("API_URL", "http://localhost:8000")
USER = "demo"          # TODO(role 4): real auth; every call already carries user_id
CATS = {"all": "All", "recipe": "Recipes", "workout": "Workouts", "place": "Places",
        "learning": "Learning", "other": "Other"}

st.set_page_config(page_title="MediaMind", page_icon="🧠", layout="centered")

st.markdown("""
<style>
.block-container {max-width: 760px; padding-top: 1.2rem;}
.mm-logo {font-size: 1.6rem; font-weight: 800; letter-spacing: -0.5px;
          background: linear-gradient(45deg,#f09433,#dc2743,#bc1888); -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;}
.mm-cap {font-size: .85rem; margin-top: -.4rem; line-height: 1.25;}
.mm-badge {display:inline-block; font-size:.7rem; padding:1px 8px; border-radius:10px;
           background:#efefef; color:#444; margin-right:4px;}
.mm-answer {border:1px solid #dbdbdb; border-radius:12px; padding:.8rem 1rem; margin:.5rem 0 1rem;}
div[data-testid="stImage"] img {border-radius: 4px; aspect-ratio: 1/1; object-fit: cover;}
</style>
""", unsafe_allow_html=True)


def api(method, path, **kw):
    try:
        r = requests.request(method, f"{API}{path}", timeout=15, **kw)
        return r
    except requests.RequestException as e:
        st.error(f"API not reachable at {API}: {e}")
        st.stop()


# ------------------------------------------------------------------ header
top = st.columns([1.2, 3.8])
top[0].markdown('<div class="mm-logo">MediaMind</div>', unsafe_allow_html=True)
question = top[1].text_input("Ask", placeholder="Ask about your saved media, e.g. which recipes need no oven?",
                             label_visibility="collapsed", key="q")

# ------------------------------------------------------------------ sidebar: approvals + upload
with st.sidebar:
    pending = api("GET", "/approvals", params={"user_id": USER}).json()
    st.subheader(f"Approvals ({len(pending)})")
    st.caption("Every save, edit, move and delete waits here for you.")
    for p in pending:
        pl = p["payload"]
        with st.container(border=True):
            st.markdown(f"**Save** · {pl['title']}  \n`{pl['category']}` · `{p['hash'][:8]}`")
            new_title = st.text_input("Title", pl["title"], key=f"t{p['id']}")
            c1, c2, c3 = st.columns(3)
            if c1.button("Approve", key=f"a{p['id']}"):
                if new_title != pl["title"]:
                    # editing voids approval: send edit first, then user must approve the new version
                    api("POST", f"/approvals/{p['id']}/edit",
                        json={"user_id": USER, "payload": {**pl, "title": new_title}})
                    st.warning("You edited it, so the earlier approval is void. Approve the new version.")
                else:
                    r = api("POST", f"/approvals/{p['id']}/approve", json={"user_id": USER})
                    st.toast("Saved" if r.ok else r.text)
                    st.rerun()
            if c2.button("Edit", key=f"e{p['id']}"):
                api("POST", f"/approvals/{p['id']}/edit",
                    json={"user_id": USER, "payload": {**pl, "title": new_title}})
                st.rerun()
            if c3.button("Reject", key=f"r{p['id']}"):
                api("POST", f"/approvals/{p['id']}/reject", json={"user_id": USER})
                st.rerun()

    st.divider()
    st.subheader("Upload")
    f = st.file_uploader("Photo or screenshot", type=["png", "jpg", "jpeg", "webp"])
    title = st.text_input("Title for this item", key="up_title")
    cat = st.selectbox("Category", [k for k in CATS if k != "all"])
    if f and st.button("Propose save"):
        r = api("POST", "/uploads/propose", json={
            "user_id": USER, "filename": f.name, "content_type": f.type or "image/png",
            "size_bytes": f.size, "title": title or f.name, "category": cat})
        if r.ok:
            pid = r.json()["proposal_id"]
            api("POST", f"/uploads/{pid}/blob", params={"user_id": USER}, data=f.getvalue())
            st.success("Waiting for your approval above.")
            st.rerun()
        else:
            st.error(r.json().get("detail", r.text))

# ------------------------------------------------------------------ search results (agent answer)
if question:
    res = api("POST", "/ask", json={"user_id": USER, "question": question}).json()
    st.markdown(f'<div class="mm-answer">🧠 {res["answer"]}'
                + (f'<br><small>Cites: {", ".join(res["citations"])}</small>' if res["citations"] else "")
                + "</div>", unsafe_allow_html=True)
    items = res["records"]
else:
    cat_choice = st.radio("Collections", list(CATS), format_func=CATS.get, horizontal=True,
                          label_visibility="collapsed")
    items = api("GET", "/items", params={"user_id": USER, "category": cat_choice}).json()

# ------------------------------------------------------------------ gallery grid
if not items:
    st.info("Nothing here yet.")
for row in range(0, len(items), 3):
    cols = st.columns(3)
    for col, it in zip(cols, items[row:row + 3]):
        with col:
            st.image(f"{API}/media/{it['media']}", width="stretch")
            tags = "".join(f'<span class="mm-badge">{t}</span>' for t in it["tags"][:2])
            st.markdown(f'<div class="mm-cap"><b>{it["title"]}</b><br>'
                        f'<span class="mm-badge">{it["category"]}</span>{tags}</div>',
                        unsafe_allow_html=True)
