from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path
import re
import sys

from groq import Groq
import instructor
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.auth import get_user_by_email
from app.config import get_settings
from app.llm import _fallback_answer
from app.rag import RagService, build_llm_context


THRESHOLDS = {
    "faithfulness": 0.80,
    "llm_context_precision_without_reference": 0.70,
    "context_recall": 0.70,
    "answer_correctness": 0.70,
}

# auto: use real Ragas LLM metrics, then fill missing judge scores with fallback.
# built_in: require real Ragas metrics and fail if the judge cannot run.
# heuristic: skip the LLM judge, useful when Groq quota is exhausted locally.
RAGAS_JUDGE_MODE = os.getenv("RAGAS_JUDGE_MODE", "auto").lower()
RAGAS_RESPONSE_MODE = os.getenv("RAGAS_RESPONSE_MODE", "auto").lower()
RAGAS_EVAL_LIMIT = int(os.getenv("RAGAS_EVAL_LIMIT", "0") or "0")
SCORE_SOURCE_COLUMN = "score_source"
SCORE_NOTE_COLUMN = "score_note"


STOPWORDS = {
    "about",
    "and",
    "are",
    "northstar",
    "can",
    "does",
    "for",
    "from",
    "how",
    "into",
    "must",
    "need",
    "needs",
    "per",
    "the",
    "this",
    "through",
    "was",
    "what",
    "when",
    "which",
    "with",
    "within",
}


def _terms(text: str) -> set[str]:
    terms = set()
    for word in re.findall(r"[a-zA-Z]+\d+|\d+(?:\.\d+)?[a-zA-Z]*|[a-zA-Z]+", str(text).lower()):
        word = word.strip(".")
        if word.endswith("ies") and len(word) > 4:
            word = f"{word[:-3]}y"
        else:
            word = word.rstrip("s")
        if len(word) < 3 and not re.fullmatch(r"[a-z]+\d+", word):
            continue
        if word in STOPWORDS:
            continue
        terms.add(word)
    return terms


def _overlap_score(reference: str, candidate: str) -> float:
    reference_terms = _terms(reference)
    if not reference_terms:
        return 0.0
    candidate_terms = _terms(candidate)
    return round(len(reference_terms & candidate_terms) / len(reference_terms), 4)


def _answer_coverage_score(answer: str, contexts: str) -> float:
    answer_terms = _terms(answer)
    if not answer_terms:
        return 0.0

    context_terms = _terms(contexts)
    unsupported_terms = answer_terms - context_terms
    return round(max(0.0, 1 - (len(unsupported_terms) / len(answer_terms))), 4)


def _build_ragas_llm():
    from ragas.llms import InstructorLLM

    settings = get_settings()
    patched_client = instructor.from_groq(Groq(api_key=settings.groq_api_key))
    return InstructorLLM(
        client=patched_client,
        model=settings.groq_model,
        provider="openai",
        temperature=0,
        max_tokens=512,
    )


def _collect_responses(dataset: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    service = RagService()
    rows = []
    samples = []
    response_mode = RAGAS_RESPONSE_MODE
    if response_mode == "auto":
        response_mode = "extractive" if RAGAS_JUDGE_MODE == "heuristic" else "app"

    for row in dataset.to_dict(orient="records"):
        user = get_user_by_email(row["user_email"])
        if user is None:
            raise ValueError(f"Unknown eval user: {row['user_email']}")

        if response_mode == "extractive":
            retrieval = service.retrieve(row["question"], user)
            contexts = [source.text for source in retrieval.sources]
            source_titles = [source.title for source in retrieval.sources]
            context = build_llm_context(row["question"], retrieval.sources)
            answer = _fallback_answer(row["question"], context)
            blocked = False
        else:
            response = service.ask(row["question"], user)
            contexts = [source.text for source in response.sources]
            source_titles = [source.title for source in response.sources]
            answer = response.answer
            blocked = response.blocked_reason is not None

        rows.append(
            {
                "question": row["question"],
                "expected_answer": row["expected_answer"],
                "actual_answer": answer,
                "response_mode": response_mode,
                "source_count": len(contexts),
                "source_titles": "; ".join(source_titles),
                "retrieved_contexts": "\n\n".join(contexts),
                "blocked": blocked,
            }
        )
        samples.append(
            {
                "user_input": row["question"],
                "response": answer,
                "reference": row["expected_answer"],
                "retrieved_contexts": contexts,
            }
        )

    return pd.DataFrame(rows), samples


def _score_with_ragas(eval_samples: list[dict]) -> pd.DataFrame:
    if RAGAS_JUDGE_MODE == "heuristic":
        raise RuntimeError("Skipping built-in Ragas LLM judge because RAGAS_JUDGE_MODE=heuristic.")

    from ragas import EvaluationDataset, SingleTurnSample, evaluate
    from ragas.embeddings import HuggingFaceEmbeddings
    from ragas.metrics._answer_correctness import AnswerCorrectness
    from ragas.metrics._context_precision import LLMContextPrecisionWithoutReference
    from ragas.metrics._context_recall import LLMContextRecall
    from ragas.metrics._faithfulness import Faithfulness

    eval_dataset = EvaluationDataset(
        samples=[
            SingleTurnSample(
                user_input=sample["user_input"],
                response=sample["response"],
                reference=sample["reference"],
                retrieved_contexts=sample["retrieved_contexts"],
            )
            for sample in eval_samples
        ]
    )
    llm = _build_ragas_llm()
    embeddings = HuggingFaceEmbeddings(model="all-MiniLM-L6-v2")
    metrics = [
        Faithfulness(llm=llm),
        LLMContextPrecisionWithoutReference(llm=llm),
        LLMContextRecall(llm=llm),
        AnswerCorrectness(llm=llm, embeddings=embeddings),
    ]

    result = evaluate(
        eval_dataset,
        metrics=metrics,
        embeddings=embeddings,
        show_progress=True,
        raise_exceptions=False,
    )
    return result.to_pandas()


def _heuristic_scores(results: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for row in results.to_dict(orient="records"):
        contexts = f"{row.get('source_titles', '')}\n\n{row.get('retrieved_contexts', '')}"
        answer_correctness = _overlap_score(row["expected_answer"], row["actual_answer"])
        context_recall = _overlap_score(row["expected_answer"], contexts)
        question_relevance = _overlap_score(row["question"], contexts)
        context_precision = max(context_recall, question_relevance)
        faithfulness = _answer_coverage_score(row["actual_answer"], contexts)

        if row["source_count"] == 0 or row["blocked"]:
            context_precision = 0.0
            context_recall = 0.0
            faithfulness = 0.0

        rows.append(
            {
                "faithfulness": faithfulness,
                "llm_context_precision_without_reference": context_precision,
                "context_recall": context_recall,
                "answer_correctness": answer_correctness,
            }
        )
    return pd.DataFrame(rows)


def _merge_scores(basic_results: pd.DataFrame, ragas_scores: pd.DataFrame | None) -> pd.DataFrame:
    score_columns = list(THRESHOLDS.keys())
    heuristic = _heuristic_scores(basic_results)
    if ragas_scores is None:
        scores = heuristic
        scores[SCORE_SOURCE_COLUMN] = "heuristic"
        scores[SCORE_NOTE_COLUMN] = "Ragas LLM judge was skipped or unavailable."
        return scores

    scores = ragas_scores.reindex(columns=score_columns).copy()
    scores = scores.reindex(range(len(basic_results))).reset_index(drop=True)
    scores[SCORE_SOURCE_COLUMN] = "ragas_llm"
    scores[SCORE_NOTE_COLUMN] = "Scored by built-in Ragas LLM metrics."
    for column in score_columns:
        missing = scores[column].isna()
        scores.loc[missing, column] = heuristic.loc[missing, column]
        scores.loc[missing, SCORE_SOURCE_COLUMN] = scores.loc[missing, SCORE_SOURCE_COLUMN].mask(
            missing,
            "heuristic_fallback",
        )
        scores.loc[missing, SCORE_NOTE_COLUMN] = scores.loc[missing, SCORE_NOTE_COLUMN].mask(
            missing,
            f"Ragas did not return {column}; deterministic fallback filled the score.",
        )
    return scores


def _write_markdown_report(results: pd.DataFrame, failures: pd.DataFrame, output_path: Path) -> None:
    metric_columns = list(THRESHOLDS.keys())
    score_source_counts = results[SCORE_SOURCE_COLUMN].value_counts().to_dict()
    lines = [
        "# Ragas Evaluation Report",
        "",
        f"Generated: {datetime.now(UTC).isoformat()}",
        f"Judge mode: {RAGAS_JUDGE_MODE}",
        f"Configured response mode: {RAGAS_RESPONSE_MODE}",
        f"Effective response modes: {results['response_mode'].value_counts().to_dict()}",
        f"Score sources: {score_source_counts}",
        "",
        "## Average Scores",
        "",
    ]

    for column in metric_columns:
        lines.append(
            f"- {column}: {results[column].mean():.3f} "
            f"(threshold {THRESHOLDS[column]:.2f})"
        )

    lines.extend(
        [
            "",
            "## Score Source Notes",
            "",
            "- `ragas_llm`: scored by Ragas using the configured Groq judge model.",
            "- `heuristic`: scored with deterministic local checks because the LLM judge was skipped or unavailable.",
            "- `heuristic_fallback`: Ragas returned partial or missing scores, usually because of quota/rate limits.",
            "",
            "## Failures",
            "",
        ]
    )
    if failures.empty:
        lines.append("No failures.")
    else:
        for row in failures.to_dict(orient="records"):
            failed_metrics = [
                column
                for column in metric_columns
                if pd.isna(row[column]) or row[column] < THRESHOLDS[column]
            ]
            lines.append(
                f"- {row['question']} | failed: {', '.join(failed_metrics)} | "
                f"source: {row[SCORE_SOURCE_COLUMN]} | documents: {row['source_titles']}"
            )

    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    dataset_path = ROOT / "evals" / "eval_dataset.csv"
    dataset = pd.read_csv(dataset_path)
    if RAGAS_EVAL_LIMIT > 0:
        dataset = dataset.head(RAGAS_EVAL_LIMIT)

    basic_results, ragas_dataset = _collect_responses(dataset)
    ragas_scores = None
    try:
        ragas_scores = _score_with_ragas(ragas_dataset)
    except Exception as exc:
        if RAGAS_JUDGE_MODE == "built_in":
            raise
        print(f"Built-in Ragas LLM scoring unavailable, using heuristic fallback: {exc}")

    score_columns = list(THRESHOLDS.keys())
    merged_scores = _merge_scores(basic_results, ragas_scores)
    results = pd.concat(
        [
            basic_results.reset_index(drop=True),
            merged_scores[[*score_columns, SCORE_SOURCE_COLUMN, SCORE_NOTE_COLUMN]].reset_index(
                drop=True
            ),
        ],
        axis=1,
    )

    latest_results_path = ROOT / "evals" / "latest_results.csv"
    ragas_report_csv_path = ROOT / "evals" / "ragas_score_report.csv"
    ragas_report_md_path = ROOT / "evals" / "ragas_score_report.md"
    results.to_csv(latest_results_path, index=False)
    results.to_csv(ragas_report_csv_path, index=False)

    metric_failures = results[
        results[score_columns].isna().any(axis=1)
        | (results[score_columns] < pd.Series(THRESHOLDS)).any(axis=1)
    ]
    structural_failures = results[(results["source_count"] == 0) | results["blocked"]]
    failures = pd.concat([metric_failures, structural_failures]).drop_duplicates()

    _write_markdown_report(results, failures, ragas_report_md_path)

    print(f"Evaluation completed. Results written to {latest_results_path}")
    print(f"Ragas scores written to {ragas_report_csv_path}")
    print(f"Ragas report written to {ragas_report_md_path}")
    for column in score_columns:
        print(f"{column}: {results[column].mean():.3f}")

    if not failures.empty:
        print(failures[["question", *score_columns, SCORE_SOURCE_COLUMN, "source_titles"]])
        raise SystemExit("Ragas evaluation failed quality thresholds.")


if __name__ == "__main__":
    main()
