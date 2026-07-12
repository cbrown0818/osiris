from __future__ import annotations

import html
import os
import re
from dataclasses import asdict, dataclass
from typing import Any

import httpx


STACK_API_BASE = "https://api.stackexchange.com/2.3"
STACK_SITE = "stackoverflow"
STACK_API_KEY = os.getenv(
    "STACKEXCHANGE_API_KEY",
    "",
).strip()

DEFAULT_TIMEOUT = httpx.Timeout(
    connect=10.0,
    read=25.0,
    write=10.0,
    pool=10.0,
)


@dataclass(frozen=True)
class StackOverflowResult:
    question_id: int
    title: str
    question_url: str
    tags: list[str]
    question_score: int
    last_activity_date: int

    answer_id: int
    answer_score: int
    is_accepted: bool
    answer_body: str
    answer_author: str
    license_name: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def strip_html(value: str) -> str:
    """
    Convert Stack Overflow HTML into readable plain text while preserving
    code blocks reasonably well.
    """

    if not value:
        return ""

    text = value

    text = re.sub(
        r"<pre><code>(.*?)</code></pre>",
        lambda match: (
            "\n\nCODE:\n"
            + html.unescape(match.group(1))
            + "\n"
        ),
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    text = re.sub(
        r"<code>(.*?)</code>",
        lambda match: (
            "`"
            + html.unescape(match.group(1))
            + "`"
        ),
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    text = re.sub(
        r"<br\s*/?>",
        "\n",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"</p>|</li>|</pre>|</blockquote>|</h[1-6]>",
        "\n",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"<li[^>]*>",
        "- ",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"<[^>]+>",
        "",
        text,
    )

    text = html.unescape(text)

    lines = [
        line.rstrip()
        for line in text.splitlines()
    ]

    cleaned_lines: list[str] = []
    previous_blank = False

    for line in lines:
        stripped = line.strip()

        if not stripped:
            if not previous_blank:
                cleaned_lines.append("")
            previous_blank = True
            continue

        cleaned_lines.append(stripped)
        previous_blank = False

    return "\n".join(cleaned_lines).strip()


def _base_params() -> dict[str, str]:
    params = {
        "site": STACK_SITE,
    }

    if STACK_API_KEY:
        params["key"] = STACK_API_KEY

    return params


async def _search_questions(
    client: httpx.AsyncClient,
    query: str,
    tags: list[str] | None,
    pagesize: int,
) -> list[dict[str, Any]]:
    params: dict[str, str | int] = {
        **_base_params(),
        "q": query,
        "pagesize": pagesize,
        "sort": "relevance",
        "order": "desc",
        "answers": 1,
    }

    if tags:
        params["tagged"] = ";".join(tags)

    response = await client.get(
        f"{STACK_API_BASE}/search/advanced",
        params=params,
    )

    response.raise_for_status()
    payload = response.json()

    return list(payload.get("items", []))


async def _fetch_answers(
    client: httpx.AsyncClient,
    question_ids: list[int],
) -> dict[int, list[dict[str, Any]]]:
    if not question_ids:
        return {}

    joined_ids = ";".join(
        str(question_id)
        for question_id in question_ids
    )

    params: dict[str, str | int] = {
        **_base_params(),
        "pagesize": min(
            max(len(question_ids) * 5, 10),
            100,
        ),
        "sort": "votes",
        "order": "desc",
        "filter": "withbody",
    }

    response = await client.get(
        (
            f"{STACK_API_BASE}/questions/"
            f"{joined_ids}/answers"
        ),
        params=params,
    )

    response.raise_for_status()
    payload = response.json()

    grouped: dict[int, list[dict[str, Any]]] = {}

    for answer in payload.get("items", []):
        question_id = int(
            answer.get("question_id", 0)
        )

        grouped.setdefault(
            question_id,
            [],
        ).append(answer)

    return grouped


def _select_best_answer(
    answers: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not answers:
        return None

    return max(
        answers,
        key=lambda answer: (
            bool(
                answer.get(
                    "is_accepted",
                    False,
                )
            ),
            int(
                answer.get(
                    "score",
                    0,
                )
            ),
        ),
    )


async def search_stackoverflow(
    query: str,
    *,
    tagged: list[str] | None = None,
    limit: int = 3,
) -> list[StackOverflowResult]:
    """
    Search Stack Overflow for questions and retrieve their best accepted
    or highest-scoring answers.
    """

    clean_query = query.strip()

    if not clean_query:
        return []

    safe_limit = max(
        1,
        min(limit, 5),
    )

    question_pagesize = min(
        max(safe_limit * 4, 8),
        20,
    )

    async with httpx.AsyncClient(
        timeout=DEFAULT_TIMEOUT,
        follow_redirects=True,
    ) as client:
        questions = await _search_questions(
            client,
            clean_query,
            tagged,
            question_pagesize,
        )

        question_ids = [
            int(question["question_id"])
            for question in questions
            if question.get("question_id")
        ]

        answers_by_question = await _fetch_answers(
            client,
            question_ids,
        )

    results: list[StackOverflowResult] = []

    for question in questions:
        question_id = int(
            question.get(
                "question_id",
                0,
            )
        )

        best_answer = _select_best_answer(
            answers_by_question.get(
                question_id,
                [],
            )
        )

        if best_answer is None:
            continue

        owner = best_answer.get(
            "owner",
            {},
        )

        results.append(
            StackOverflowResult(
                question_id=question_id,
                title=html.unescape(
                    question.get(
                        "title",
                        "",
                    )
                ),
                question_url=question.get(
                    "link",
                    "",
                ),
                tags=list(
                    question.get(
                        "tags",
                        [],
                    )
                ),
                question_score=int(
                    question.get(
                        "score",
                        0,
                    )
                ),
                last_activity_date=int(
                    question.get(
                        "last_activity_date",
                        0,
                    )
                ),
                answer_id=int(
                    best_answer.get(
                        "answer_id",
                        0,
                    )
                ),
                answer_score=int(
                    best_answer.get(
                        "score",
                        0,
                    )
                ),
                is_accepted=bool(
                    best_answer.get(
                        "is_accepted",
                        False,
                    )
                ),
                answer_body=strip_html(
                    best_answer.get(
                        "body",
                        "",
                    )
                ),
                answer_author=html.unescape(
                    owner.get(
                        "display_name",
                        "Unknown contributor",
                    )
                ),
                license_name=best_answer.get(
                    "content_license",
                    question.get(
                        "content_license",
                        "CC BY-SA",
                    ),
                ),
            )
        )

        if len(results) >= safe_limit:
            break

    return results


def format_stackoverflow_context(
    results: list[StackOverflowResult],
    *,
    max_chars_per_answer: int = 2200,
) -> str:
    """
    Format retrieved sources for use inside a language-model prompt.
    """

    if not results:
        return (
            "No relevant Stack Overflow "
            "sources were found."
        )

    sections: list[str] = []

    for index, result in enumerate(
        results,
        start=1,
    ):
        body = result.answer_body[
            :max_chars_per_answer
        ]

        sections.append(
            "\n".join(
                [
                    (
                        f"Stack Overflow source "
                        f"{index}"
                    ),
                    f"Title: {result.title}",
                    f"URL: {result.question_url}",
                    (
                        "Accepted answer: "
                        f"{result.is_accepted}"
                    ),
                    (
                        "Answer score: "
                        f"{result.answer_score}"
                    ),
                    (
                        "Tags: "
                        f"{', '.join(result.tags)}"
                    ),
                    (
                        "Contributor: "
                        f"{result.answer_author}"
                    ),
                    (
                        "License: "
                        f"{result.license_name}"
                    ),
                    "Retrieved answer text:",
                    body,
                ]
            )
        )

    return "\n\n---\n\n".join(sections)
