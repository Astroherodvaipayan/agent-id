import html
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from pydantic import BaseModel
from . import core
from . import studio, negotiations, coordinator
from .agntid_gate import protected_send
from .inbox import poll
from .planner import ModelUnconfigured, plan_campaign, suggest_from_reply
from .wyld_search import search as wyld_search, configured as wyld_configured
from .local_config import load_local_config

@asynccontextmanager
async def lifespan(_app):
    load_local_config()
    yield

app = FastAPI(title="AgentID Campaign Desk", lifespan=lifespan)

@app.get("/assets/wyld-bg-neon-night.webp")
def wyld_background():
    return FileResponse(Path(__file__).with_name("web") / "wyld-bg-neon-night.webp", media_type="image/webp")

@app.get("/assets/creator-brief.js")
def creator_brief_script():
    return FileResponse(Path(__file__).with_name("web") / "creator-brief.js", media_type="text/javascript")

@app.get('/assets/negotiations.js')
def negotiations_script():
    return FileResponse(Path(__file__).with_name('web') / 'negotiations.js', media_type='text/javascript')

@app.get('/assets/demo-email.js')
def demo_email_script():
    return FileResponse(Path(__file__).with_name('web') / 'demo-email.js', media_type='text/javascript')

@app.middleware("http")
async def operator_guard(request: Request, call_next):
    if request.url.path in ("/", "/trust", "/pitch", "/creator-demo", "/docs", "/openapi.json", "/assets/wyld-bg-neon-night.webp", "/assets/creator-brief.js", "/assets/negotiations.js", "/assets/demo-email.js"):
        return await call_next(request)
    token = os.getenv("OPERATOR_TOKEN")
    if not token:
        return JSONResponse({"detail": "Set OPERATOR_TOKEN before accessing campaign data or actions"}, status_code=503)
    supplied = request.headers.get("Authorization", "").removeprefix("Bearer ")
    if not secrets.compare_digest(token, supplied):
        return JSONResponse({"detail": "Operator authorization required"}, status_code=401)
    if request.method not in ("GET", "HEAD"):
        origin = request.headers.get("Origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            return JSONResponse({"detail": "Cross-origin mutation denied"}, status_code=403)
    return await call_next(request)

class Campaign(BaseModel):
    idea: str
    creator: str
    budget_paise: int
    target_markets: list[str]
    avoid_terms: list[str] = []
    creator_intro: str = ""

class MarketReview(BaseModel):
    revision: int
    reviewer: str
    mitigation: str

class Approval(BaseModel):
    revision: int
    amount_paise: int
    approver: str
    preview_hash: str

class Send(BaseModel):
    operation_id: str
    amount_paise: int

class DemoReply(BaseModel):
    revision: int
    body: str

class VerifyInbound(BaseModel):
    uid: str
    source: str
    provider_record_id: str
    sender_verified: bool
    thread_verified: bool
    operator: str

class Reconcile(BaseModel):
    operation_id: str
    status: str
    evidence: str
    operator: str

@app.post("/campaign")
def campaign(v: Campaign):
    try:
        return core.draft(v.idea, v.creator, v.budget_paise, creator_intro=v.creator_intro, target_markets=v.target_markets, avoid_terms=v.avoid_terms)
    except (ValueError, KeyError) as e:
        raise HTTPException(400, str(e))

@app.post("/campaign/ai")
def campaign_ai(v: Campaign):
    try:
        if v.creator.strip().lower() != os.getenv("CREATOR_EMAIL", "").strip().lower():
            raise ValueError("Creator is outside the configured recipient allowlist")
        if not v.target_markets:
            raise ValueError("At least one target market is required")
        if not 0 < v.budget_paise <= core.CEILING:
            raise ValueError("Campaign budget outside supported range")
        plan = plan_campaign(v.idea, v.target_markets, v.avoid_terms)
        suggested = min(plan["suggested_budget_paise"], v.budget_paise)
        # The brand's total budget is the campaign limit. A model fee estimate
        # is review data and must not silently replace that limit.
        saved = core.draft(v.idea, v.creator, v.budget_paise, plan["brief"], plan["creator_intro"], v.target_markets, v.avoid_terms, plan["risk_flags"])
        return {**saved, "model_rationale": plan["rationale"], "model_state": "configured", "brand_budget_paise": v.budget_paise, "suggested_budget_paise": suggested}
    except ModelUnconfigured as e:
        raise HTTPException(503, str(e))
    except (ValueError, KeyError) as e:
        raise HTTPException(400, str(e))

@app.post("/guardrails/review")
def guardrails_review(v: MarketReview):
    try:
        core.review_guardrails(v.revision, v.reviewer, v.mitigation)
        return {"reviewed": True, "revision": v.revision}
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.post("/negotiate/suggest")
def negotiate_suggest():
    try:
        reply = core.latest_reply()
        return suggest_from_reply(reply["idea"], reply["body"])
    except ModelUnconfigured as e:
        raise HTTPException(503, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.post("/approve")
def approve(v: Approval):
    try:
        core.approve(v.revision, v.amount_paise, v.approver, v.preview_hash)
        return {"approved": True}
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.get("/proposal/preview")
def proposal_preview(amount_paise: int):
    try:
        return core.preview_payload(amount_paise)
    except (ValueError, KeyError) as e:
        raise HTTPException(400, str(e))

@app.post("/send")
async def send(v: Send):
    if os.getenv("DEMO_MODE") == "1":
        raise HTTPException(403, "Demo mode cannot send email")
    try:
        # Check backend approval before opening an AgntID task. The MCP handler checks again.
        core.proposal_payload(v.amount_paise)
        return await protected_send(v.operation_id, v.amount_paise)
    except (ValueError, PermissionError) as e:
        raise HTTPException(403, str(e))

@app.post("/inbox/poll")
def inbox_poll():
    if os.getenv("DEMO_MODE") == "1":
        raise HTTPException(403, "Demo mode has no real inbox")
    return {"seen": poll()}

@app.post("/demo/suggest")
def demo_suggest(v: DemoReply):
    if os.getenv("DEMO_MODE") != "1":
        raise HTTPException(404, "Demo mode is disabled")
    if not v.body.strip() or len(v.body) > 10000:
        raise HTTPException(400, "Enter a mock creator reply of at most 10,000 characters")
    c = core.db()
    try:
        campaign = c.execute("SELECT idea,revision FROM campaign WHERE id=1").fetchone()
        if not campaign or campaign["revision"] != v.revision:
            raise HTTPException(400, "Create the current campaign first")
        idea = campaign["idea"]
    finally:
        c.close()
    try:
        return suggest_from_reply(idea, v.body)
    except ModelUnconfigured as e:
        raise HTTPException(503, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.post("/inbox/verify")
def inbound_verify(v: VerifyInbound):
    try:
        core.verify_inbound(v.uid, v.source, v.provider_record_id, v.sender_verified, v.thread_verified, v.operator)
        return {"verified": True}
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.post("/outbox/reconcile")
def reconcile(v: Reconcile):
    try:
        return core.record_reconciliation(v.operation_id, v.status, v.evidence, v.operator)
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.get("/creators/search")
def creators_search(q: str, page: int = 1, page_size: int = 25, followers_min: int | None = None, engagement_rate_min: float | None = None):
    try:
        filters={key:value for key,value in {'followers_min':followers_min,'engagement_rate_min':engagement_rate_min}.items() if value is not None}
        result = wyld_search(q,page,page_size,filters)
        studio.record_discovery(result)
        return result
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))

class StudioDetails(BaseModel):
    revision: int
    name: str = ""
    brand_name: str = ""
    category: str = ""
    target_audience: str = ""
    campaign_window: str = ""
    notes: str = ""

class ShortlistItem(BaseModel):
    revision: int
    username: str
    quoted_paise: int | None = None
    negotiated_paise: int | None = None
    notes: str = ""
    remove: bool = False

@app.post("/studio/details")
def studio_details(v: StudioDetails):
    try:
        return studio.save_details(v.revision, v.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc))

@app.post("/studio/shortlist")
def studio_shortlist(v: ShortlistItem):
    try:
        studio.shortlist(**v.model_dump())
        return studio.snapshot()
    except ValueError as exc:
        raise HTTPException(400, str(exc))

@app.get("/state")
def state():
    c = core.db()
    try:
        data = {t: [dict(r) for r in c.execute(f"SELECT * FROM {t} ORDER BY id DESC LIMIT 50")] if t == "events" else [dict(r) for r in c.execute(f"SELECT * FROM {t}")] for t in ("campaign", "guardrail_review", "approval", "outbox", "inbound", "reconciliation", "events")}
        data["readiness"] = {"outbound_ready": all(os.getenv(x) for x in ("SMTP_HOST", "SMTP_FROM", "CREATOR_EMAIL", "BRAND_REPLY_TO", "AGNTID_MCP_URL")), "inbound_ready": all(os.getenv(x) for x in ("IMAP_HOST", "IMAP_USERNAME", "IMAP_PASSWORD", "CREATOR_EMAIL")), "model_ready": all(os.getenv(x) for x in ("GEMINI_API_KEY", "GEMINI_MODEL")), "wyld_search_configured": wyld_configured()}
        data["studio"] = studio.snapshot()
        data["negotiation"] = negotiations.snapshot()
        return data
    finally:
        c.close()

@app.get("/workspace/config")
def workspace_config():
    return {"controlled_creator_email": os.getenv("CREATOR_EMAIL", ""), "gemini_ready": all(os.getenv(x) for x in ("GEMINI_API_KEY", "GEMINI_MODEL")), "wyld_search_ready": wyld_configured(), "demo_mode": os.getenv("DEMO_MODE") == "1"}

@app.get("/", response_class=HTMLResponse)
def dashboard():
    return Path(__file__).with_name("web").joinpath("index.html").read_text()


class CreatorLane(BaseModel):
    revision: int
    creator_handle: str
    recipient: str
    operator: str
    evidence: str

class LaneAction(BaseModel):
    negotiation_id: str
    revision: int = 0
    operator: str
    evidence: str

class LaneProposal(BaseModel):
    negotiation_id: str
    amount_paise: int
    preview_hash: str = ''
    operator: str = ''

class RunCreators(BaseModel):
    negotiation_ids: list[str]
    operator: str

class ReconcileCreator(BaseModel):
    operation_id: str
    outcome: str
    operator: str
    evidence: str

class VerifyCreatorReply(BaseModel):
    uid: str
    operator: str
    evidence: str

class ConfirmCreator(BaseModel):
    negotiation_id: str
    revision: int
    operation_id: str
    operator: str
    agreement_reference: str

@app.post('/negotiations/create')
def create_lane(v: CreatorLane):
    try:return {'negotiation_id':negotiations.create(**v.model_dump())}
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.post('/negotiations/reveal')
def reveal_lane(v: LaneAction):
    try:
        negotiations.reveal(v.negotiation_id,v.revision,v.operator,v.evidence)
        return {'status':'brand_reveal_approved'}
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.post('/negotiations/cancel')
def cancel_lane(v: LaneAction):
    try:
        negotiations.cancel(v.negotiation_id,v.operator,v.evidence)
        return {'status':'cancelled','uncertain_sends':'reservation retained pending reconciliation'}
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.post('/negotiations/preview')
def preview_lane(v: LaneProposal):
    try:return negotiations.preview(v.negotiation_id,v.amount_paise)
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.post('/negotiations/approve')
def approve_lane(v: LaneProposal):
    try:return negotiations.approve(v.negotiation_id,v.amount_paise,v.preview_hash,v.operator)
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.post('/negotiations/run')
async def run_lanes(v: RunCreators):
    if os.getenv("DEMO_MODE") == "1":
        raise HTTPException(403, "Demo mode cannot dispatch creator email")
    try:return await coordinator.run(v.negotiation_ids,v.operator)
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.post('/negotiations/reconcile')
def reconcile_lane(v: ReconcileCreator):
    try:
        negotiations.reconcile(v.operation_id,v.outcome,v.operator,v.evidence)
        return {'status':'reconciled'}
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.post('/negotiations/replies/verify')
def verify_creator_reply(v: VerifyCreatorReply):
    try:return negotiations.verify_reply(**v.model_dump())
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.post('/negotiations/confirm')
def confirm_creator(v: ConfirmCreator):
    try:
        negotiations.confirm(v.negotiation_id,v.revision,v.operation_id,v.operator,v.agreement_reference)
        return {'status':'external_agreement_human_verified','automated_binding_action':False}
    except ValueError as exc:raise HTTPException(400,str(exc))


class PrepareRound(BaseModel):
    negotiation_id: str
    reply_uid: str
    operator: str
    supersession_evidence: str

class TerminateLane(BaseModel):
    negotiation_id: str
    reason: str
    operator: str
    evidence: str

@app.post('/negotiations/rounds/prepare')
def prepare_creator_round(v: PrepareRound):
    try:return negotiations.prepare_round(v.negotiation_id,v.reply_uid,v.operator,v.supersession_evidence)
    except ValueError as exc:raise HTTPException(400,str(exc))
    except ModelUnconfigured as exc:raise HTTPException(503,str(exc))

@app.post('/negotiations/terminate')
def terminate_creator(v: TerminateLane):
    try:
        negotiations.terminate(v.negotiation_id,v.reason,v.operator,v.evidence)
        return {'status':'terminated','reservation':'only before-dispatch releases automatically'}
    except ValueError as exc:raise HTTPException(400,str(exc))


@app.get('/pitch', response_class=HTMLResponse)
def pitch_homepage():
    return Path(__file__).with_name('web').joinpath('pitch.html').read_text()


@app.get('/creator-demo', response_class=HTMLResponse)
def creator_demo():
    return Path(__file__).with_name('web').joinpath('creator-demo.html').read_text()



@app.get('/creators')
def public_creator_list(page: int = 1, page_size: int = 25):
    if os.getenv('WYLD_PROVIDER','local')!='public':raise HTTPException(503,'Select the public creator provider locally')
    from .wyld_public import list_creators
    try:
        result=list_creators(page,page_size)
        studio.record_discovery(result)
        return result
    except ValueError as exc:raise HTTPException(400,str(exc))
    except RuntimeError as exc:raise HTTPException(503,str(exc))

@app.get('/creators/profile/{username}')
def public_creator_profile(username: str):
    if os.getenv('WYLD_PROVIDER','local')!='public':raise HTTPException(503,'Select the public creator provider locally')
    from .wyld_public import get_creator
    try:return get_creator(username)
    except ValueError as exc:raise HTTPException(400,str(exc))
    except RuntimeError as exc:raise HTTPException(503,str(exc))


@app.get("/trust", response_class=HTMLResponse)
def trust_evidence_page():
    return Path(__file__).with_name("web").joinpath("trust.html").read_text()
