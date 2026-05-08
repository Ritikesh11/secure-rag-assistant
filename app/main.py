from pathlib import Path
import re

import streamlit as st

from app.audit import FeedbackEvent, append_feedback_event
from app.admin import deactivate_user, parse_departments, save_uploaded_document, upsert_user
from app.auth import authenticate, get_user_by_email, list_demo_credentials
from app.config import get_settings
from app.dashboard import read_csv_rows, total_cost
from app.health import collect_health_checks
from app.ingest import ingest
from app.rag import RagService, RetrievedSource, is_document_listing_request
from app.rbac import Classification, UserProfile, load_user_records


def _login_view() -> UserProfile | None:
    st.title("Northstar Analytics Internal RAG Chatbot")

    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in")

    if submitted:
        user = authenticate(email, password)
        if user:
            st.session_state.user_email = user.email
            st.session_state.messages = []
            st.rerun()
        st.error("Invalid email or password.")

    with st.expander("Demo logins"):
        for credential in list_demo_credentials():
            st.code(f"{credential.email} / {credential.password_hint}", language=None)

    return None


def _apply_chat_layout() -> None:
    st.markdown(
        """
        <style>
        section.main > div {
            padding-bottom: 6rem;
        }
        div[data-testid="stChatInput"] {
            position: fixed;
            bottom: 0;
            left: 21rem;
            right: 1rem;
            z-index: 999;
            background: var(--background-color);
            padding-top: 0.5rem;
            padding-bottom: 0.75rem;
        }
        @media (max-width: 900px) {
            div[data-testid="stChatInput"] {
                left: 1rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _current_user() -> UserProfile | None:
    email = st.session_state.get("user_email")
    if not email:
        return None

    return get_user_by_email(email)


def _normalize_chat_answer(answer: str) -> str:
    normalized = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", answer.strip())
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized


def _render_profile_card(user: UserProfile) -> None:
    initials = "".join(part[0] for part in (user.display_name or user.email).split()[:2]).upper()
    st.markdown(
        f"""
        <div style="border:1px solid rgba(128,128,128,.25);border-radius:8px;padding:14px;margin-bottom:12px;">
          <div style="display:flex;gap:10px;align-items:center;">
            <div style="width:42px;height:42px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:#1f6feb;color:white;font-weight:700;">
              {initials}
            </div>
            <div>
              <div style="font-weight:700;">{user.display_name or user.email}</div>
              <div style="font-size:13px;opacity:.75;">{user.title or user.role.title()}</div>
            </div>
          </div>
          <div style="font-size:13px;margin-top:12px;opacity:.85;">{user.email}</div>
          <div style="font-size:13px;margin-top:6px;">Role: <b>{user.role}</b></div>
          <div style="font-size:13px;">Departments: <b>{", ".join(user.departments)}</b></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_dashboard(settings, service: RagService) -> None:
    usage_rows = read_csv_rows(settings.usage_log_path, limit=200)
    audit_rows = read_csv_rows(settings.audit_log_path, limit=200)
    feedback_rows = read_csv_rows(settings.feedback_log_path, limit=200)

    usage_col, audit_col, feedback_col = st.columns(3)
    usage_col.metric("Estimated Cost", f"${total_cost(usage_rows):.6f}")
    audit_col.metric("Audit Events", len(audit_rows))
    feedback_col.metric("Feedback Items", len(feedback_rows))

    if total_cost(usage_rows) >= settings.cost_alert_daily_usd:
        st.warning(f"Estimated cost is above alert threshold: ${settings.cost_alert_daily_usd:.2f}")

    st.subheader("Health")
    for check in collect_health_checks(settings, service.collection_count()):
        icon = "OK" if check.ok else "Needs attention"
        st.caption(f"{icon}: {check.name} - {check.detail}")

    st.subheader("Recent Audit Events")
    if audit_rows:
        st.dataframe(audit_rows, use_container_width=True)
    else:
        st.info("No audit events yet. Ask the chatbot a question to create one.")

    st.subheader("Recent Usage")
    if usage_rows:
        st.dataframe(usage_rows, use_container_width=True)
    else:
        st.info("No usage events yet.")

    st.subheader("Feedback")
    if feedback_rows:
        st.dataframe(feedback_rows, use_container_width=True)
    else:
        st.info("No feedback submitted yet.")


def _render_admin(settings) -> None:
    st.subheader("User Management")
    records = load_user_records(settings.user_store_path)
    st.dataframe(
        [
            {
                "email": record["email"],
                "name": record.get("display_name", ""),
                "title": record.get("title", ""),
                "role": record.get("role", ""),
                "departments": ", ".join(record.get("departments", [])),
                "active": record.get("active", True),
            }
            for record in records.values()
        ],
        use_container_width=True,
    )

    with st.expander("Add or edit user"):
        with st.form("upsert_user"):
            email = st.text_input("Email")
            display_name = st.text_input("Display name")
            title = st.text_input("Title")
            role = st.selectbox("Role", ["employee", "admin", "executive"])
            departments = st.text_input("Departments", value="finance")
            password = st.text_input("New password", type="password")
            active = st.checkbox("Active", value=True)
            submitted = st.form_submit_button("Save user")
        if submitted:
            try:
                upsert_user(
                    settings.user_store_path,
                    email=email,
                    display_name=display_name,
                    title=title,
                    role=role,
                    departments=parse_departments(departments),
                    active=active,
                    password=password or None,
                )
                st.success("User saved. They can sign in after refresh.")
            except ValueError as exc:
                st.error(str(exc))

    with st.expander("Deactivate user"):
        email_to_disable = st.selectbox("User", sorted(records.keys()), key="disable_user_email")
        if st.button("Deactivate selected user"):
            deactivate_user(settings.user_store_path, email_to_disable)
            st.success("User deactivated.")

    st.subheader("Document Upload")
    uploaded_file = st.file_uploader("Upload .txt, .md, or .pdf", type=["txt", "md", "pdf"])
    doc_department = st.selectbox(
        "Department",
        ["company", "finance", "hr", "marketing", "engineering", "legal", "executive"],
    )
    doc_classification = st.selectbox(
        "Classification",
        [item.value for item in Classification],
        index=1,
    )
    if st.button("Save and index document", disabled=uploaded_file is None):
        try:
            path = save_uploaded_document(
                settings.upload_dir,
                uploaded_file,
                department=doc_department,
                classification=doc_classification,
            )
            count = ingest(settings.upload_dir, reset=False)
            st.success(f"Saved {path.name} and indexed {count} uploaded chunks.")
            st.info("Ask for the document by title, topic, department, or file name.")
        except Exception as exc:
            st.error(str(exc))


def _source_title(source: RetrievedSource) -> str:
    source_path = Path(source.source)
    return source.title or source_path.stem.replace("-", " ").replace("_", " ").title()


def _render_source_download(source: RetrievedSource, key_suffix: str, show_preview: bool) -> None:
    source_path = Path(source.source)
    title = _source_title(source)
    st.markdown(f"**{title}**  \n{source.department} / {source.classification}")

    if source.distance is not None:
        st.caption(f"Retrieval distance: {source.distance:.3f}")

    if show_preview:
        st.text(source.text[:700])

    if source_path.exists():
        st.download_button(
            "Open / Download document",
            data=source_path.read_bytes(),
            file_name=source_path.name,
            key=f"download_{source.source}_{key_suffix}",
        )


def _chat_placeholder(user: UserProfile) -> str:
    if user.is_executive or user.can_manage_documents:
        return "Ask anything from your authorized company knowledge base"
    departments = ", ".join(department.title() for department in user.departments)
    return f"Ask about your {departments} documents or company policies"


def _render_chat(user: UserProfile, service: RagService, settings) -> None:
    _apply_chat_layout()
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    question = st.chat_input(_chat_placeholder(user))
    if not question:
        st.info("Ask an internal company question. Your login controls which sources are available.")
        return

    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Retrieving authorized context..."):
            response = service.ask(question, user)
        answer = _normalize_chat_answer(response.answer)
        st.markdown(answer)

        if response.blocked_reason:
            st.warning(response.blocked_reason)

        if response.denied_source_count and user.can_view_monitoring:
            st.caption("Some unavailable context was excluded from this response.")

        if response.usage and user.can_view_monitoring:
            st.caption(
                f"Tokens: {response.usage.prompt_tokens + response.usage.completion_tokens} | "
                f"Estimated cost: ${response.usage.cost_usd:.6f}"
            )

        feedback_key_base = str(len(st.session_state.messages))
        if response.sources:
            if is_document_listing_request(question):
                st.subheader("Documents")
                for index, source in enumerate(response.sources):
                    with st.container(border=True):
                        _render_source_download(
                            source,
                            key_suffix=f"{feedback_key_base}_{index}",
                            show_preview=False,
                        )
            else:
                with st.expander("Authorized source previews"):
                    for index, source in enumerate(response.sources):
                        _render_source_download(
                            source,
                            key_suffix=f"{feedback_key_base}_{index}",
                            show_preview=True,
                        )

        feedback_col_1, feedback_col_2 = st.columns(2)
        if feedback_col_1.button("Helpful", key=f"helpful_{feedback_key_base}"):
            append_feedback_event(
                settings.feedback_log_path,
                FeedbackEvent(user.email, question, answer, "helpful"),
            )
            st.toast("Feedback saved.")
        if feedback_col_2.button("Needs work", key=f"needs_work_{feedback_key_base}"):
            append_feedback_event(
                settings.feedback_log_path,
                FeedbackEvent(user.email, question, answer, "needs_work"),
            )
            st.toast("Feedback saved.")

    st.session_state.messages.append({"role": "assistant", "content": answer})


def run() -> None:
    st.set_page_config(page_title="Northstar Analytics Internal RAG", page_icon="N", layout="wide")
    settings = get_settings()

    user = _current_user()
    if not user:
        _login_view()
        return

    st.title("Northstar Analytics Internal RAG Chatbot")

    with st.sidebar:
        _render_profile_card(user)
        if st.button("Sign out", use_container_width=True):
            st.session_state.pop("user_email", None)
            st.session_state.messages = []
            st.rerun()
        if user.can_view_monitoring:
            st.divider()
            st.caption(f"Model: {settings.groq_model}")

    service = RagService(settings)

    if user.can_manage_users or user.can_manage_documents:
        chat_tab, monitor_tab, admin_tab = st.tabs(["Chat", "Monitoring", "Admin"])
        with chat_tab:
            _render_chat(user, service, settings)
        with monitor_tab:
            _render_dashboard(settings, service)
        with admin_tab:
            _render_admin(settings)
    elif user.can_view_monitoring:
        chat_tab, monitor_tab = st.tabs(["Chat", "Monitoring"])
        with chat_tab:
            _render_chat(user, service, settings)
        with monitor_tab:
            _render_dashboard(settings, service)
    else:
        _render_chat(user, service, settings)
