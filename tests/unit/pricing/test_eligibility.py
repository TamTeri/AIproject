from __future__ import annotations

import pytest

from app.pricing.config import temporary_local_policy
from app.pricing.eligibility import (
    EligibilityError,
    EventFacts,
    IdentityFacts,
    evaluate_student_eligibility,
    normalize_email,
)


@pytest.fixture
def local_policy():
    return temporary_local_policy()


def test_normalize_email_trims_and_casefolds_without_plus_aliasing():
    assert normalize_email("  Student.Name+tag@USF.EDU  ") == "student.name+tag@usf.edu"


@pytest.mark.parametrize(
    "email",
    [
        "",
        "missing-at-sign",
        "two@@signs.usf.edu",
        "student@",
        "@usf.edu",
        "student @usf.edu",
        "student@usf.edu\n",
    ],
)
def test_normalize_email_rejects_malformed_values(email: str):
    with pytest.raises(EligibilityError):
        normalize_email(email)


def test_exact_usf_domain_is_eligible_after_normalization(local_policy):
    decision = evaluate_student_eligibility(
        IdentityFacts(email="  Student@USF.EDU  "),
        EventFacts(event_id="event-1"),
        local_policy,
    )

    assert decision.eligible is True
    assert decision.normalized_email == "student@usf.edu"
    assert decision.policy_revision == local_policy.revision


@pytest.mark.parametrize(
    "email",
    [
        "student@mail.usf.edu",
        "student@usf.edu.",
        "student+tag@usf.edu",
        "student@example.edu",
    ],
)
def test_temporary_rule_rejects_subdomains_trailing_dot_plus_tags_and_other_domains(
    email: str, local_policy
):
    decision = evaluate_student_eligibility(
        IdentityFacts(email=email),
        EventFacts(event_id="event-1"),
        local_policy,
    )

    assert decision.eligible is False


def test_malformed_email_fails_closed_without_raising_from_eligibility_seam(local_policy):
    decision = evaluate_student_eligibility(
        IdentityFacts(email="not-an-email"),
        EventFacts(event_id="event-1"),
        local_policy,
    )

    assert decision.eligible is False
    assert decision.reason == "invalid_email"
