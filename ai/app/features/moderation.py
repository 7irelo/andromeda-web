"""
Content moderation as a deterministic workflow, not an agent.

    stage 0  OpenAI omni-moderation (free): generic harm signal
    stage 1  Claude Haiku with Andromeda's policy rubric (structured output)
    stage 2  Claude Sonnet, only when stage 1 is unsure or the stages disagree
    fallback when every model is unavailable, fail closed for new accounts
             (hold for review) and open for established ones (allow, audit later)

Decisions: allow | review (a human looks at it) | remove (hidden immediately,
the author is told and can appeal).
"""
import logging
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from .. import metrics
from ..gateway import AllRoutesFailed, BudgetExceeded, Gateway, ProviderError, Refused
from ..guardrails import UNTRUSTED_NOTICE, untrusted

logger = logging.getLogger(__name__)

ESCALATE_BELOW = 0.75
STAGE0_SEVERE = 0.85
NEW_ACCOUNT_DAYS = 7


class Decision(StrEnum):
    ALLOW = 'allow'
    REVIEW = 'review'
    REMOVE = 'remove'


Category = Literal['none', 'spam', 'scam', 'harassment', 'hate', 'sexual', 'violence', 'self_harm',
                   'illegal_goods', 'personal_data', 'other']


class Verdict(BaseModel):
    decision: Literal['allow', 'review', 'remove']
    categories: list[Category] = Field(description='Policy categories that apply; ["none"] when clean.')
    confidence: float = Field(ge=0, le=1, description='How sure you are of the decision.')
    reason: str = Field(max_length=300, description='One short sentence for the moderator log.')


class ModerationRequest(BaseModel):
    content_type: Literal['post', 'comment', 'listing', 'message', 'profile']
    text: str = Field(max_length=20_000)
    account_age_days: int = Field(ge=0, default=365)


class ModerationResult(BaseModel):
    decision: Decision
    categories: list[str]
    confidence: float
    reason: str
    stages: list[str]
    model: str | None = None
    cost_usd: float = 0.0
    degraded: bool = False


POLICY = f"""You are the content-safety classifier for Andromeda, a South African social network
with a marketplace. Classify the user content against this policy.

{UNTRUSTED_NOTICE}

Remove (clear violations):
- scams: advance-fee fraud, fake giveaways, phishing links, "send money first" marketplace fraud
- illegal goods or services: weapons, drugs, counterfeit documents, stolen goods, wildlife products
- credible threats of violence, incitement, or glorification of violent attacks
- sexual content involving minors (always remove), or explicit sexual content
- hate speech: attacks on people for race, ethnicity, religion, gender, sexuality, disability or nationality,
  including slurs used as insults
- doxxing: someone else's ID number, home address or phone number shared without consent

Review (a human should look):
- borderline or ambiguous cases, satire that could be read as a threat, heated arguments,
  self-harm content (to route support), suspicious but unproven sales, repetitive promotion

Allow:
- everything else, including strong opinions, profanity that isn't aimed at a person,
  reclaimed language used about oneself, news reporting, and normal buying and selling

Users write in English, isiZulu, isiXhosa, Afrikaans, Sesotho, Setswana and mixtures of them.
Judge meaning, not keywords. Give your decision, the categories that apply ("none" if clean),
your confidence, and one short reason."""


def _merge(stage0: dict | None, verdict: Verdict) -> tuple[Decision, list[str]]:
    decision = Decision(verdict.decision)
    cats = [c for c in verdict.categories if c != 'none']
    if stage0 and stage0['flagged'] and decision == Decision.ALLOW:
        # The generic classifier and the policy model disagree: let a human decide.
        decision = Decision.REVIEW
        cats.append(f"stage0:{stage0['top_category']}")
    return decision, cats


async def moderate(req: ModerationRequest, gateway: Gateway, user_id: int, stage0_provider=None) -> ModerationResult:
    text = req.text.strip()
    if not text:
        return ModerationResult(decision=Decision.ALLOW, categories=[], confidence=1.0,
                                reason='Empty content', stages=['empty'])

    stages: list[str] = []
    stage0 = None
    if stage0_provider is not None:
        try:
            stage0 = await stage0_provider.moderate(text[:10_000])
            stages.append('omni-moderation')
        except ProviderError:
            logger.warning('Stage 0 moderation unavailable')

    user_msg = untrusted(text, 10_000, kind=req.content_type)
    total_cost = 0.0
    try:
        first = await gateway.structured('moderation.classify', system=POLICY, user=user_msg,
                                         schema=Verdict, user_id=user_id)
        stages.append(first.model)
        total_cost += first.cost_usd
        result, model = first.output, first.model
        decision, cats = _merge(stage0, result)
        unsure = result.confidence < ESCALATE_BELOW and result.decision != 'allow'
        disagree = decision != Decision(result.decision)
        severe0 = bool(stage0 and stage0['top_score'] >= STAGE0_SEVERE and result.decision == 'allow')
        if unsure or disagree or severe0:
            second = await gateway.structured('moderation.escalate', system=POLICY, user=user_msg,
                                              schema=Verdict, user_id=user_id)
            stages.append(second.model)
            total_cost += second.cost_usd
            result, model = second.output, second.model
            decision, cats = _merge(stage0, result)
    except Refused:
        # A model refusing to engage with the content is itself a strong signal.
        metrics.DECISIONS.labels('review').inc()
        return ModerationResult(decision=Decision.REVIEW, categories=['model_refused'], confidence=0.5,
                                reason='Classifier declined to process this content', stages=stages + ['refused'],
                                cost_usd=total_cost)
    except (AllRoutesFailed, BudgetExceeded) as exc:
        fallback = Decision.REVIEW if req.account_age_days < NEW_ACCOUNT_DAYS else Decision.ALLOW
        if stage0 and stage0['flagged']:
            fallback = Decision.REVIEW
        metrics.DECISIONS.labels(fallback.value).inc()
        return ModerationResult(decision=fallback, categories=[], confidence=0.0,
                                reason=f'Models unavailable ({type(exc).__name__}); policy fallback',
                                stages=stages + ['fallback'], cost_usd=total_cost, degraded=True)

    metrics.DECISIONS.labels(decision.value).inc()
    return ModerationResult(decision=decision, categories=cats, confidence=result.confidence,
                            reason=result.reason, stages=stages, model=model, cost_usd=round(total_cost, 6))
