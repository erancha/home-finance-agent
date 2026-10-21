#!/usr/bin/env python3
"""Drive a monthly review through the running home finance agent and amex-agent, as a person would.

The person first signs in: the script signs ID tokens with the private key whose public half both
agents trust (make_auth.py), one for the home finance agent's client id, posted to its session
route the way the page posts Google's credential, and one for amex-agent's own client id, for the
statements page. Without the first the review API answers 401; without the second the statements
API does.

amex-agent starts with an empty statements folder, so the October review first pauses on its
request for the missing statement: a question that links to the agent's statements page and
offers only "continue". The script loads amex-agent's test statement through that page's API, as
the page would, into the person's own folder, and continues. The review must then pause on one
categorize question for the gym, the one merchant the agent's keyword categorizer does not know;
answered "health", it must finish with totals and a report. Each check prints a PASS: line; the
first failure prints the frames seen so far and exits 1.

The gym question appears only while the home finance agent's merchant memory has not learnt it,
so the script needs a database no earlier run has answered it in.

    backend/.venv/bin/python scripts/tests/e2e/run_review.py http://localhost:8010 <statement.pdf> \
        <auth-private.pem>
"""
from __future__ import annotations

import json
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx
import jwt

EVENT_TIMEOUT_SECONDS = 90.0
STATUS_TIMEOUT_SECONDS = 30.0
# The server sends a keepalive comment every 15 s, so a read longer than this means it is stuck.
READ_TIMEOUT_SECONDS = 30.0
MONTH = "2026-10"
STATEMENTS_API = "/api/statements"
# The issuer and client ids docker-compose.e2e.yml hands both agents, and the person reviewing.
ISSUER = "hfm-e2e"
HFM_CLIENT_ID = "hfm-e2e-client"
AMEX_CLIENT_ID = "amex-e2e-client"
PERSON = {"sub": "1000", "email": "e2e@example.com", "name": "E2E"}
# The one merchant of amex-agent's test statement (src/test/resources/statements/2026-10.pdf) its
# keyword categorizer does not know, and the health total once its single October charge joins.
GYM_MERCHANT = 'וים קלאבס בע"מ - הו"'
HEALTH_SPENT = str(Decimal("1248.82") + Decimal("307.78"))


class E2EFailure(Exception):
    pass


def id_token(private_key: Path, audience: str) -> str:
    """An ID token for the person, issued to one client, valid an hour, as Google would sign it."""
    now = int(time.time())
    claims = {**PERSON, "iss": ISSUER, "aud": audience, "iat": now, "exp": now + 3600}
    return jwt.encode(claims, private_key.read_bytes(), algorithm="RS256")


def sign_in(client: httpx.Client, token: str) -> None:
    """The review API refuses a stranger; the session route turns the token into the cookie."""
    refused = client.get(f"/api/months/{MONTH}")
    check(refused.status_code == 401, "the review API refuses a person who is not signed in",
          refused.status_code)
    response = client.post("/api/auth/session", json={"credential": token})
    expect_status(response, 200, "sign in to the home finance agent")
    check(response.json()["id"] == PERSON["sub"], "the sign-in names the person", response.json())


@dataclass(frozen=True)
class Frame:
    seq: int
    type: str
    data: dict[str, Any]


def parse_frames(lines: Iterator[str]) -> Iterator[Frame | None]:
    """Server-sent event frames, with None for each comment line (keepalive) so a reader waiting
    on a quiet stream still gets to check its deadline."""
    fields: dict[str, str] = {}
    for line in lines:
        if line.startswith(":"):
            yield None
            continue
        if line:
            name, _, value = line.partition(":")
            fields[name] = value.removeprefix(" ")
            continue
        if fields:
            yield Frame(int(fields["id"]), fields["event"], json.loads(fields["data"]))
            fields = {}


class ReviewSession:
    """One review: its id, an open event stream and every frame read from it."""

    def __init__(self, client: httpx.Client, month: str) -> None:
        self._client = client
        self.month = month
        response = client.post("/api/reviews", json={"month": month})
        expect_status(response, 202, f"start the {month} review")
        self.id: str = response.json()["id"]
        self.seen: list[Frame] = []
        self._stream = client.stream("GET", f"/api/reviews/{self.id}/events")
        response = self._stream.__enter__()
        expect_status(response, 200, "open the event stream")
        self._frames = parse_frames(response.iter_lines())

    def close(self) -> None:
        self._stream.__exit__(None, None, None)

    def read_until(self, event_type: str) -> Frame:
        deadline = time.monotonic() + EVENT_TIMEOUT_SECONDS
        try:
            for frame in self._frames:
                if frame is not None:
                    self.seen.append(frame)
                    if frame.type == "review.failed":
                        raise E2EFailure(f"review {self.month} failed: {frame.data}")
                    if frame.type == event_type:
                        return frame
                    if frame.type == "review.report":
                        raise E2EFailure(f"review {self.month} finished without a {event_type}")
                if time.monotonic() > deadline:
                    break
        except httpx.HTTPError as error:
            raise E2EFailure(f"event stream broke waiting for {event_type}: {error!r}") from error
        raise E2EFailure(f"no {event_type} within {EVENT_TIMEOUT_SECONDS:g} s")

    def last(self, event_type: str) -> Frame:
        matching = [f for f in self.seen if f.type == event_type]
        if not matching:
            raise E2EFailure(f"no {event_type} frame was streamed")
        return matching[-1]

    def wait_until_waiting(self) -> None:
        """The question event goes out before the review records that it is waiting."""
        deadline = time.monotonic() + STATUS_TIMEOUT_SECONDS
        while True:
            response = self._client.get(f"/api/reviews/{self.id}")
            expect_status(response, 200, "read the review")
            status = response.json()["status"]
            if status == "waiting":
                return
            if time.monotonic() > deadline:
                raise E2EFailure(f"status still {status!r} after {STATUS_TIMEOUT_SECONDS:g} s")
            time.sleep(0.5)

    def answer(self, answers: dict[str, str], expected: int = 204) -> None:
        response = self._client.post(
            f"/api/reviews/{self.id}/answers", json={"answers": answers}
        )
        expect_status(response, expected, f"answer {answers}")


def expect_status(response: httpx.Response, expected: int, action: str) -> None:
    if response.status_code != expected:
        raise E2EFailure(
            f"{action}: {response.request.method} {response.request.url} returned "
            f"{response.status_code}, expected {expected}: {response.text}"
        )


def check(condition: bool, message: str, detail: Any) -> None:
    if not condition:
        raise E2EFailure(f"{message}: {json.dumps(detail, ensure_ascii=False)}")
    print(f"PASS: {message}")


def by_category(totals_frame: Frame) -> dict[str, dict[str, Any]]:
    return {t["category"]: t for t in totals_frame.data["totals"]}


def single_question(frame: Frame, kind: str) -> dict[str, Any]:
    questions = frame.data["questions"]
    check(
        len(questions) == 1 and questions[0]["kind"] == kind,
        f"the review asks exactly one {kind} question",
        questions,
    )
    question: dict[str, Any] = questions[0]
    return question


def load_missing_statement(review: ReviewSession, statement: Path, amex_token: str) -> None:
    question = single_question(review.read_until("review.question"), "remote-input")
    check(question["agent"] == "amex", "the statement request comes from amex", question)
    check(question["reason"] == "statement-missing", "the request is for the statement", question)
    check(question["actions"] == ["continue"], "the request offers only continue", question)
    link = question["link"]
    page = httpx.get(link)
    check(
        page.status_code == 200 and page.headers["content-type"].startswith("text/html"),
        "the request links to the agent's statements page",
        {"link": link, "status": page.status_code},
    )
    review.wait_until_waiting()
    print("PASS: the review is waiting for answers")
    review.answer({question["id"]: "skip"}, expected=422)
    print("PASS: the answer skip is refused")
    statements_api = urljoin(link, STATEMENTS_API)
    anonymous = httpx.get(statements_api)
    check(anonymous.status_code == 401, "the statements API refuses a person who is not signed in",
          anonymous.status_code)
    as_person = {"Authorization": f"Bearer {amex_token}"}
    upload = httpx.post(
        statements_api,
        headers=as_person,
        files={"file": (statement.name, statement.read_bytes(), "application/pdf")},
    )
    expect_status(upload, 201, "load the statement through the statements page API")
    check(
        upload.json()["fileName"] == f"{review.month}.pdf",
        "the agent stores the statement under its billing month",
        upload.json(),
    )
    listed = httpx.get(statements_api, headers=as_person)
    expect_status(listed, 200, "list the person's statements")
    check(
        [s["fileName"] for s in listed.json()] == [f"{review.month}.pdf"],
        "the statement is listed for the person who loaded it",
        listed.json(),
    )
    review.answer({question["id"]: "continue"})
    print("PASS: the answer continue is accepted")


def categorized_review(review: ReviewSession) -> None:
    question = single_question(review.read_until("review.question"), "categorize")
    check(question["merchant"] == GYM_MERCHANT, "the question is about the gym", question)
    review.wait_until_waiting()
    print("PASS: the review is waiting for answers")
    review.answer({question["id"]: "health"})
    print("PASS: the answer is accepted")
    report = review.read_until("review.report")
    totals = by_category(review.last("review.totals"))
    check(
        "uncategorized" not in totals or totals["uncategorized"]["spent"] == "0.00",
        "no spend is left uncategorized",
        totals,
    )
    check(
        "health" in totals and totals["health"]["spent"] == HEALTH_SPENT,
        f"the answer moved the gym into health, now {HEALTH_SPENT}",
        totals,
    )
    check(bool(report.data["text"].strip()), "the report has text", report.data)


def run(base_url: str, statement: Path, private_key: Path) -> None:
    timeout = httpx.Timeout(10.0, read=READ_TIMEOUT_SECONDS)
    with httpx.Client(base_url=base_url, timeout=timeout) as client:
        sign_in(client, id_token(private_key, HFM_CLIENT_ID))
        print(f"--- review {MONTH}")
        review = ReviewSession(client, MONTH)
        try:
            load_missing_statement(review, statement, id_token(private_key, AMEX_CLIENT_ID))
            categorized_review(review)
        except E2EFailure:
            print(f"FAIL in review {MONTH} ({review.id}); frames seen:", file=sys.stderr)
            for frame in review.seen:
                line = json.dumps(frame.data, ensure_ascii=False)
                print(f"  {frame.seq} {frame.type} {line}", file=sys.stderr)
            raise
        finally:
            review.close()


def main() -> int:
    if len(sys.argv) != 4:
        print(
            f"usage: {sys.argv[0]} <manager base url> <statement.pdf> <auth-private.pem>",
            file=sys.stderr,
        )
        return 2
    try:
        run(sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]))
    except E2EFailure as failure:
        print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("PASS: the review completed end to end")
    return 0


if __name__ == "__main__":
    sys.exit(main())
