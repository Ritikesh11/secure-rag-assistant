# Improvements Roadmap

## Added In The Local Demo

- Login screen with department-specific demo users.
- Hashed demo passwords instead of plain password storage.
- Local JSON user store with admin add/edit/deactivate support.
- Admin document upload for `.txt`, `.md`, and `.pdf`.
- Download buttons for authorized source documents.
- RBAC-controlled retrieval based on the logged-in user.
- Prompt-injection and access-bypass guardrails.
- PII redaction for retrieved context and final answers.
- Audit logging for answered and blocked questions.
- Denied-access signals when a question targets another department.
- Token and estimated cost logging.
- Monitoring tab with health checks, audit events, usage, cost, and feedback for executive/admin users only.
- Source previews for authorized retrieved chunks.
- Helpful / needs-work feedback buttons.
- CI workflow for unit tests, ingestion, and RAG regression evals.

## Best Upgrades When Moving To Cloud

- Replace demo auth with Microsoft Entra ID / Azure AD.
- Map Entra groups to app roles and departments.
- Store secrets in Azure Key Vault.
- Replace local Chroma with Qdrant Cloud, Azure AI Search, or managed PostgreSQL + pgvector.
- Send audit, feedback, usage, and app logs to Azure Monitor / Log Analytics.
- Create Azure Monitor alerts for cost spikes, blocked requests, error rates, and latency.
- Add private networking between app, vector store, and document storage.
- Add admin document upload with malware scanning and approval workflow.
- Use Docling for PDF, DOCX, PPTX, scanned documents, and table extraction.
- Add document-level ACLs synced from SharePoint, OneDrive, or internal file systems.
- Add automatic re-indexing when source documents change.
- Add LangSmith tracing for prompt, retrieval, model latency, and evaluation tracking.
- Add full Ragas scoring for faithfulness, answer relevancy, context recall, and context precision.
- Add deployment gates that fail releases when eval quality drops below thresholds.
- Add human review queues for low-confidence answers and negative feedback.
- Add encryption-at-rest policies and retention rules for logs.
- Add rate limits by user, department, and environment.
- Add production SSO logout/session expiry.
- Add tenant-aware architecture if multiple client companies use the system.
