from app.rag import (
    RetrievedSource,
    build_llm_context,
    filter_relevant_sources,
    format_document_list,
    is_document_listing_request,
)


def test_remote_policy_question_keeps_remote_policy_source_only() -> None:
    remote = RetrievedSource(
        text="Northstar Analytics employees may work remotely up to three days per week.",
        source="data/sample_docs/company/internal/remote-work-policy.md",
        department="company",
        classification="internal",
        title="Remote Work Policy",
        distance=0.4,
    )
    marketing = RetrievedSource(
        text="The marketing team spent USD 420K on the North America awareness campaign.",
        source="data/sample_docs/marketing/confidential/campaign-expenses.md",
        department="marketing",
        classification="confidential",
        title="Marketing Campaign Expenses",
        distance=0.8,
    )

    filtered = filter_relevant_sources("What is the remote work policy?", [remote, marketing])

    assert filtered == [remote]


def test_remote_policy_question_ignores_document_catalog() -> None:
    remote = RetrievedSource(
        text="Northstar Analytics employees may work remotely up to three days per week with manager approval.",
        source="data/sample_docs/company/internal/remote-work-policy.md",
        department="company",
        classification="internal",
        title="Remote Work Policy",
        distance=0.5,
    )
    catalog = RetrievedSource(
        text="Available company documents include the Remote Work Policy, Security and AI Usage Policy, and Company Document Catalog.",
        source="data/sample_docs/company/internal/document-catalog.md",
        department="company",
        classification="internal",
        title="Company Document Catalog",
        distance=0.4,
    )

    filtered = filter_relevant_sources("What is the remote work policy?", [catalog, remote])

    assert filtered == [remote]


def test_marketing_typo_keeps_marketing_source() -> None:
    marketing = RetrievedSource(
        text="The Q1 content calendar includes four customer webinars.",
        source="department-marketing__classification-confidential__brand_and_content_calendar.md",
        department="marketing",
        classification="confidential",
        distance=0.4,
    )
    finance = RetrievedSource(
        text="Finance projects FY revenue of USD 74M.",
        source="department-finance__classification-confidential__annual_planning_forecast.md",
        department="finance",
        classification="confidential",
        distance=0.8,
    )

    filtered = filter_relevant_sources("What is the markting calendar?", [marketing, finance])

    assert filtered == [marketing]


def test_detects_document_listing_request() -> None:
    assert is_document_listing_request("fetch me all the documents of marketing department")
    assert is_document_listing_request("show finance pdfs")
    assert is_document_listing_request("what documents can I access?")
    assert is_document_listing_request("what files do I have?")
    assert not is_document_listing_request("what is the marketing budget?")
    assert not is_document_listing_request("what does the marketing document say about webinars?")
    assert not is_document_listing_request("summarize the marketing document")
    assert not is_document_listing_request("what is in the finance document catalog?")


def test_format_document_list() -> None:
    source = RetrievedSource(
        text="Marketing content",
        source="data/sample_docs/marketing/confidential/brand-and-content-calendar.md",
        department="marketing",
        classification="confidential",
        title="Brand And Content Calendar",
    )

    answer = format_document_list([source])

    assert "Use the download buttons below" in answer
    assert "Brand And Content Calendar" in answer


def test_build_llm_context_keeps_relevant_sentence_only() -> None:
    source = RetrievedSource(
        text=(
            "# Remote Work Policy\n\n"
            "Northstar Analytics employees may work remotely up to three days per week with manager approval. "
            "All employees must use company-managed devices for client data."
        ),
        source="data/sample_docs/company/internal/remote-work-policy.md",
        department="company",
        classification="internal",
        title="Remote Work Policy",
    )

    context = build_llm_context("what is the remote work policy?", [source])

    assert "three days per week" in context
    assert "company-managed devices" not in context
