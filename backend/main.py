import io
import json
import os

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import pdfplumber
from anthropic import Anthropic
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

if not os.environ.get("ANTHROPIC_API_KEY"):
    raise RuntimeError(
        "ANTHROPIC_API_KEY is not set.\n"
        "Run: export ANTHROPIC_API_KEY=your-api-key  (Linux/Mac)\n"
        "  or: set ANTHROPIC_API_KEY=your-api-key    (Windows cmd)\n"
        "  or: $env:ANTHROPIC_API_KEY='your-api-key' (PowerShell)"
    )

app = FastAPI(title="AI Safety Careers Advisor")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
client = Anthropic()

QUESTIONS = [
    {
        "id": 1,
        "question": "How familiar are you with core AI safety concepts (e.g., alignment, inner misalignment, interpretability)?",
        "type": "scale",
        "options": [
            "Not familiar at all",
            "I've heard the terms",
            "Basic understanding",
            "Understand the key debates",
            "Follow the research closely",
        ],
    },
    {
        "id": 2,
        "question": "Which types of AI safety materials have you engaged with? Select all that apply.",
        "type": "multi",
        "options": [
            "Academic papers (e.g., Concrete Problems in AI Safety)",
            "Books (e.g., Superintelligence, Human Compatible)",
            "Online courses (e.g., AGI Safety Fundamentals)",
            "Podcasts or video content",
            "80,000 Hours articles / career guides",
            "Blog posts (Alignment Forum, LessWrong)",
            "None yet",
        ],
    },
    {
        "id": 3,
        "question": "What is your experience level with machine learning or AI development?",
        "type": "scale",
        "options": [
            "No experience",
            "Conceptual understanding only",
            "Completed courses or tutorials",
            "Built personal ML projects",
            "Work professionally with ML/AI",
        ],
    },
    {
        "id": 4,
        "question": "How much time per week can you realistically dedicate to AI safety activities?",
        "type": "scale",
        "options": [
            "Less than 2 hours",
            "2–5 hours",
            "5–10 hours",
            "10–20 hours",
            "Full-time commitment",
        ],
    },
    {
        "id": 5,
        "question": "What kind of contribution do you most want to make to AI safety? What's your primary goal?",
        "type": "text",
        "placeholder": "e.g., 'I want to do technical alignment research', 'I want to shape AI policy', 'I want to understand where I can have the most impact'...",
    },
]

AI_SAFETY_PROGRAMS = """**BlueDot Impact – AI Safety Fundamentals (Technical Track)**
An 8-week facilitated online course covering alignment fundamentals: reward misspecification, RLHF, interpretability, robustness. Best for those with some programming background. Free, runs multiple cohorts per year. Mostly for people new to AI safety or considering transitioning into the field. A common next step after BlueDot is a deeper-engagement opportunity like ARENA, MATS, or Astra fellowship. Selective — does not accept everyone. Time commitment: ~5–8 hours/week for 8 weeks (part-time friendly). aisafetyfundamentals.com

**BlueDot Impact – AI Governance Fundamentals**
An 8-week course covering AI governance, policy, and safety from a non-technical perspective. Ideal for policy, legal, and social-science backgrounds. Free. Mostly for people new to AI safety or considering transitioning. Selective. Time commitment: ~5–8 hours/week for 8 weeks (part-time friendly).

**AISF Self-Paced Reading Groups**
Community-run reading groups following the AI Safety Fundamentals curriculum. Flexible timing, both technical and governance tracks available. Low commitment, good for exploring before joining intensive programs. Time commitment: ~2–3 hours/week, flexible schedule.

**ARENA (Alignment Research Engineer Accelerator)**
Intensive technical upskilling program focused on ML engineering for alignment research. Many participants join after completing a BlueDot course or other introductory steps. After ARENA, people typically move on to high-engagement programs like MATS or Astra before landing their first AI safety job. Requires programming and ML foundations. Time commitment: full-time.

**MATS (ML Alignment Theory Scholars)**
Competitive 3-month research program pairing scholars with senior alignment researchers (Anthropic, DeepMind, ARC). Requires strong ML/research background. Stipend provided. Very competitive. Time commitment: full-time. matsprogram.org

**Astra Fellowship (Constellation)**
A fully-funded, in-person fellowship (3–6 months) at Constellation's Berkeley research center that pairs emerging researchers with senior advisors. Project focus areas include technical safety, governance, strategy, and field-building. Best for people who have already taken initial steps in AI safety (e.g., completed BlueDot or ARENA) and want intensive mentorship. Very competitive. Time commitment: full-time. constellation.org/programs/astra

**Constellation Visiting Fellowship**
A lightly-structured, funded fellowship (3–6 months) for full-time AI safety researchers to work from Constellation's Berkeley research center and connect with the broader network. Best for researchers already working in AI safety who want access to a collaborative environment and strong network. Time commitment: full-time. constellation.org/programs/visiting-fellowship

**Constellation Incubator**
A 4-month program designed to build the next wave of organizations addressing advanced AI risks. Provides funding, operational support, and access to Constellation's expert network. Best for people with a concrete org-building idea related to AI safety. Time commitment: full-time. constellation.org/programs/incubator

**Constellation General Hosting & Visitors**
Short-term visiting and ongoing workspace access at Constellation's Berkeley research center for individuals, teams, and established organizations aligned with the AI safety mission. Good for networking and short collaborative stints. Time commitment: flexible (days to weeks). constellation.org/contact

**Future Impact Group (FIG)**
Very high bar, very personalized fellowship. FIG identifies what talents and skillsets specific projects need, then headhunts matching candidates. Part-time & remote format designed for working professionals. Currently working on 3 projects with Yoshua Bengio: (1) insurance and liability as levers for AI safety, (2) AI-driven concentration of power and economic sovereignty, (3) military AI and threats to AI safety. Time commitment: part-time, remote (compatible with a full-time job).

**AI Safety Camp**
Project-based research retreats (~2 weeks) where small teams tackle concrete alignment problems. Some technical background required. Good stepping stone before MATS. Time commitment: full-time for ~2 weeks.

**Apart Research**
AI safety hackathons (online, 1–3 days) and longer fellowships. Open to varied backgrounds including governance, interpretability, and conceptual work. Low barrier to entry, good for building an initial research portfolio. Time commitment: 1–3 days per hackathon (part-time friendly).

**80,000 Hours AI Safety Career Advising**
Free 1-on-1 coaching to identify the highest-impact AI safety path for your specific background. Strongly recommended as an early step for anyone uncertain about direction. Their website (80000hours.org) is the best source of knowledge about qualifications needed for different AI safety roles, with excellent profile descriptions. Their job board lists AI safety-related positions. Time commitment: minimal (one-off calls). 80000hours.org/speak-with-us

**GovAI Fellowship (Centre for the Governance of AI)**
Fellowships for policy, legal, and social-science professionals focused on AI governance research. Oxford-based and remote. Very competitive — receives several thousand applications per edition. High bar for applicants. Time commitment: full-time.

**Successif**
Provides support for professionals transitioning into AI safety careers. Great at helping with the transition process, including upskilling, network-building, and navigating the AI safety job market. Time commitment: flexible.

**CAIS (Center for AI Safety)**
Technical workshops, research support, and the ML Safety course. Resources at safe.ai. Technical focus. Time commitment: varies (self-paced course is part-time friendly).

**Alignment Forum and LessWrong**
Online communities central to AI safety research discourse. Writing and engaging here builds network and credibility. Essential reading for those pursuing technical alignment. Having LessWrong background and context can significantly accelerate a career transition into AI safety. Time commitment: flexible, self-directed."""


class QuestionAnswer(BaseModel):
    question_id: int
    answer: str


class RecommendationRequest(BaseModel):
    cv_summary: str
    answers: list[QuestionAnswer]


class FollowUpRequest(BaseModel):
    question: str
    recommendations: str
    chat_history: list[dict] = []


@app.get("/api/questions")
async def get_questions():
    return {"questions": QUESTIONS}


@app.post("/api/classify-cv")
async def classify_cv(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File size exceeds 10 MB limit.")

    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            cv_text = "\n".join(
                page.extract_text() or "" for page in pdf.pages
            ).strip()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse PDF: {e}")

    if not cv_text:
        raise HTTPException(
            status_code=400,
            detail="No text found in this PDF. It may be image-based (scanned). Please use a text-based PDF.",
        )

    return {
        "cv_summary": cv_text[:1000],
    }


@app.post("/api/get-recommendations")
async def get_recommendations(request: RecommendationRequest):
    answers_formatted = []
    for ans in request.answers:
        q = next((q for q in QUESTIONS if q["id"] == ans.question_id), None)
        if q:
            answers_formatted.append(f"**{q['question']}**\n{ans.answer}")

    answers_text = "\n\n".join(answers_formatted)

    def stream_response():
        with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=(
                "You are an expert AI safety career advisor. "
                "You MUST start your response with the first program recommendation immediately. "
                "FORBIDDEN: any title, heading, greeting, introduction, summary, or preamble before the first program. "
                "FORBIDDEN: using the user's name anywhere. Always say 'you'/'your', never third person. "
                "Your first characters must be a bold program name like **Program Name**.\n\n"
                "## Key guidelines\n"
                "- Prioritize the user's GOALS over their background. Find ways to combine their background with their stated goal creatively. "
                "For example, if someone has a policy background but wants to do fieldbuilding, suggest they could organize AI policy fellowships — "
                "that uses their skillset and applies it to their goal.\n"
                "- Fieldbuilding and governance/policy are DISTINCT types of work. DO NOT mistake these two. "
                "Fieldbuilding includes organizing courses, fellowships, events, improving talent flow, career advisory, recruitment, and community management. "
                "Governance/policy is about improving legal regulations of AI and the political landscape. Never confuse or conflate these two.\n"
                "- Not everyone wants to do research. Do NOT suggest research fellowships to people who want to do other work "
                "(e.g., communications, fieldbuilding, operations). Instead, suggest looking for entry-level or junior roles of the relevant type in AI safety.\n"
                "- BlueDot Impact courses are mostly for people new to AI safety or considering transitioning into the field. "
                "A common next step after BlueDot is a deeper-engagement opportunity like ARENA, MATS, or the Astra fellowship.\n"
                "- AI safety opportunities are quite competitive (often one in a few dozen candidates is accepted, even BlueDot is selective). "
                "Building a track record matters — e.g., organizing an AI safety university group, attending conferences, doing small projects.\n"
                "- Students and alumni of top universities (Harvard, MIT, etc.) and people with major STEM achievements "
                "(e.g., International Math Olympiad winners, ex-CERN employees) are strongly preferred in competitive programs.\n"
                "- People with a PhD in CS or significant professional experience (e.g., cybersecurity researchers, research managers in tech) "
                "may be accepted to fellowships even without prior AI safety involvement. More junior candidates (e.g., undergrads) face a higher bar — "
                "they typically need a track record in the AI safety community, strong understanding of threat models, references, or exceptional educational achievements.\n"
                "- Typical transition timeline for experienced professionals from outside AIS: 6–18 months to upskill, join the network, build trust, and complete small projects. "
                "Sometimes 2–3 months if the person is free full-time and already has LessWrong background/context. Successif is great at supporting the transition process.\n"
                "- A typical progression path is: BlueDot → ARENA → MATS/Astra Fellowship → first AI safety job.\n"
                "- Constellation (constellation.org) runs several programs in Berkeley: the Astra Fellowship (mentored research, 3–6 months), "
                "Visiting Fellowship (for established researchers), Incubator (for org-builders), and General Hosting (short visits/workspace). "
                "Recommend the appropriate Constellation program based on the user's stage and goals.\n"
                "- The 80,000 Hours website (80000hours.org) is the best source of knowledge about qualifications needed for different AI safety roles. "
                "They have excellent profile descriptions. Their job board lists AI safety positions. Recommend it as a resource when relevant.\n"
                "- In rare occasions, orgs might hire a good professional from outside the community and train them in AI safety.\n"
                "- CRITICAL: Respect the user's stated time availability. "
                "If someone can commit less than 10 hours per week, do NOT recommend full-time programs "
                "(MATS, ARENA, Astra Fellowship, Visiting Fellowship, Constellation Incubator, AI Safety Camp). "
                "Instead, recommend part-time-friendly options: BlueDot courses, AISF reading groups, Apart Research hackathons, "
                "80,000 Hours advising, Alignment Forum/LessWrong, FIG (part-time/remote), or self-paced resources. "
                "For users with 2–5 hours/week, focus on low-commitment entry points. "
                "Only suggest full-time programs as aspirational next steps IF the user indicates they may increase availability in the future."
            ),
            messages=[
                {
                    "role": "user",
                    "content": (
                        "## Background\n"
                        f"**CV excerpt:** {request.cv_summary[:600]}\n\n"
                        "## Self-Assessment\n"
                        f"{answers_text}\n\n"
                        "## Available Programs\n"
                        f"{AI_SAFETY_PROGRAMS}\n\n"
                        "## Task\n"
                        "Recommend 3–5 programs. For each:\n"
                        "1. Bold the program name as a heading\n"
                        "2. Explain specifically WHY it fits me (reference my background, experience, time, and goals)\n"
                        "3. Note what I'll gain and any prerequisites or application tips\n\n"
                        "Order by most immediately accessible first. Be specific, honest, and encouraging. "
                        "If I have limited time, acknowledge it and suggest the most efficient options.\n\n"
                        "Remember: start directly with the first **Program Name**, no intro."
                    ),
                },
            ],
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {json.dumps({'text': text})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        stream_response(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/follow-up")
async def follow_up(request: FollowUpRequest):
    messages = [
        {
            "role": "user",
            "content": (
                f"I received these program recommendations:\n{request.recommendations[:2000]}\n\n"
                "I have a follow-up question about these opportunities."
            ),
        },
        {
            "role": "assistant",
            "content": "I'd be happy to answer any questions about the programs recommended to you. What would you like to know?",
        },
    ]

    for msg in request.chat_history:
        messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append({"role": "user", "content": request.question})

    def stream_response():
        with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=(
                "You are an expert AI safety career advisor. "
                "Answer follow-up questions about AI safety programs concisely and helpfully. "
                "Reference specific details about programs when relevant. "
                "Always address the user as 'you'. Keep answers focused and practical.\n\n"
                "## Key domain knowledge\n"
                "- Fieldbuilding (organizing courses, fellowships, events, talent flow, career advisory, recruitment, community management) "
                "and governance/policy (legal regulations, political landscape) are DISTINCT types of work. Never confuse them.\n"
                "- Not everyone wants research — suggest entry-level/junior roles for people interested in comms, fieldbuilding, ops, etc.\n"
                "- Typical career progression: BlueDot → ARENA → MATS/Astra Fellowship → first AI safety job.\n"
                "- Constellation runs programs in Berkeley: Astra Fellowship (mentored research, 3–6 months), "
                "Visiting Fellowship (established researchers), Incubator (org-builders), General Hosting (short visits).\n"
                "- Transition timeline for experienced professionals: typically 6–18 months; sometimes 2–3 months if full-time with LessWrong background.\n"
                "- Top universities and major STEM achievements strongly preferred in competitive programs. "
                "PhD holders in CS and experienced tech professionals may get in without prior AI safety involvement. "
                "More junior candidates need stronger AI safety track records.\n"
                "- 80000hours.org is the best resource for role profiles and job listings. Successif helps with career transitions.\n"
                "- FIG (Future Impact Group) has a very high bar, personalized approach, part-time/remote for working professionals, "
                "currently running 3 projects with Yoshua Bengio.\n"
                "- GovAI receives several thousand applications per edition.\n"
                "- In rare cases, orgs may hire good professionals from outside the community and train them."
            ),
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {json.dumps({'text': text})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        stream_response(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# Mount frontend — must come AFTER all API routes
_frontend = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(_frontend):
    app.mount("/", StaticFiles(directory=_frontend, html=True), name="frontend")
