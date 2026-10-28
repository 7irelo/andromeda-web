"""
Content moderation as a deterministic workflow, not an agent.

    stage 0  OpenAI omni-moderation (free): generic harm signal
    stage ½  distilled classifier (optional): a confident "allow" skips the LLM;
             anything else, or anything stage 0 flagged, continues
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

Review (a human should look). Choose review, not allow, for:
- conditional or veiled threats, and protest language that talks about damaging or shutting down places
- put-downs aimed at a person or a group without a slur, including telling someone to leave or that
  nobody wants them around
- generalisations that blame a nationality or other group for social problems, short of a direct attack
- any sign the writer may harm themselves (hopelessness, saying goodbye, giving belongings away), so
  support can reach them
- marketplace listings with fraud signals but no proof: price far below market, payment before seeing
  the item, refusing to meet, vague or suspicious origin, prescription medicines
- repetitive self-promotion, or money-making offers that ask for personal details
- trying to find out where a named person lives or can be found

Allow:
- everything else, including strong opinions, profanity that isn't aimed at a person,
  reclaimed language used about oneself, news reporting, sports trash talk, figures of speech
  ("that exam killed me"), peaceful protest announcements, sharing helplines, and normal buying and selling

Users write in English, isiZulu, isiXhosa, Afrikaans, Sesotho, Setswana and mixtures of them.
Judge meaning, not keywords. Give your decision, the categories that apply ("none" if clean),
your confidence, and one short reason."""


# The stronger model can overrule a stage-0 flag only when it's this sure the
# content is fine (news headlines and sports talk trip the generic classifier).
OVERRULE_STAGE0_AT = 0.85


def _merge(stage0: dict | None, verdict: Verdict, final: bool = False) -> tuple[Decision, list[str]]:
    decision = Decision(verdict.decision)
    cats = [c for c in verdict.categories if c != 'none']
    if stage0 and stage0['flagged'] and decision == Decision.ALLOW:
        if final and verdict.confidence >= OVERRULE_STAGE0_AT:
            cats.append(f"stage0_overruled:{stage0['top_category']}")
        else:
            # The generic classifier and the policy model disagree: escalate, then let a human decide.
            decision = Decision.REVIEW
            cats.append(f"stage0:{stage0['top_category']}")
    return decision, cats


async def moderate(req: ModerationRequest, gateway: Gateway, user_id: int, stage0_provider=None,
                   student=None) -> ModerationResult:
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

    total_cost = 0.0
    if student is not None and not (stage0 and stage0['flagged']):
        try:
            emb = await gateway.embed('search.embed', texts=[text[:8000]], user_id=user_id)
            total_cost += emb.cost_usd
            ok, p_allow = student.confident_allow(emb.vectors[0])
            stages.append('distilled')
            if ok:
                metrics.DECISIONS.labels('allow').inc()
                return ModerationResult(decision=Decision.ALLOW, categories=[], confidence=round(p_allow, 3),
                                        reason='Distilled classifier: confidently within policy', stages=stages,
                                        model='distilled-v1', cost_usd=round(total_cost, 6))
        except (ProviderError, AllRoutesFailed, BudgetExceeded):
            logger.warning('Distilled stage skipped: embeddings unavailable')

    user_msg = untrusted(text, 10_000, kind=req.content_type)
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
            decision, cats = _merge(stage0, result, final=True)
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
