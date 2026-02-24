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
        "question": "Describe any AI safety materials you've engaged with — papers, books, courses, podcasts. Write 'None yet' if you're just starting.",
        "type": "text",
        "placeholder": "e.g., 'Concrete Problems in AI Safety', Superintelligence, 80,000 Hours articles, AGI Safety Fundamentals course...",
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
An 8-week facilitated online course covering alignment fundamentals: reward misspecification, RLHF, interpretability, robustness. Best for those with some programming background. Free, runs multiple cohorts per year. aisafetyfundamentals.com

**BlueDot Impact – AI Governance Fundamentals**
An 8-week course covering AI governance, policy, and safety from a non-technical perspective. Ideal for policy, legal, and social-science backgrounds. Free.

**AISF Self-Paced Reading Groups**
Community-run reading groups following the AI Safety Fundamentals curriculum. Flexible timing, both technical and governance tracks available. Low commitment, good for exploring before joining intensive programs.

**MATS (ML Alignment Theory Scholars)**
Competitive 3-month research program pairing scholars with senior alignment researchers (Anthropic, DeepMind, ARC). Requires strong ML/research background. Stipend provided. matsprogram.org

**AI Safety Camp**
Project-based research retreats (~2 weeks) where small teams tackle concrete alignment problems. Some technical background required. Good stepping stone before MATS.

**Apart Research**
AI safety hackathons (online, 1–3 days) and longer fellowships. Open to varied backgrounds including governance, interpretability, and conceptual work. Low barrier to entry, good for building an initial research portfolio.

**80,000 Hours AI Safety Career Advising**
Free 1-on-1 coaching to identify the highest-impact AI safety path for your specific background. Strongly recommended as an early step for anyone uncertain about direction. 80000hours.org/speak-with-us

**GovAI Fellowship (Centre for the Governance of AI)**
Fellowships for policy, legal, and social-science professionals focused on AI governance research. Oxford-based and remote. Highly competitive.

**CAIS (Center for AI Safety)**
Technical workshops, research support, and the ML Safety course. Resources at safe.ai. Technical focus.

**Alignment Forum and LessWrong**
Online communities central to AI safety research discourse. Writing and engaging here builds network and credibility. Essential reading for those pursuing technical alignment."""


class QuestionAnswer(BaseModel):
    question_id: int
    answer: str


class RecommendationRequest(BaseModel):
    cv_category: str
    cv_summary: str
    answers: list[QuestionAnswer]


class FollowUpRequest(BaseModel):
    question: str
    cv_category: str
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

    # Truncate to ~3 500 tokens of input
    cv_text_truncated = cv_text[:14000]

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Analyse this CV and classify the person into exactly one of these categories:\n"
                        "- computer science student\n"
                        "- experienced ML professional\n"
                        "- professional with legal background\n"
                        "- policy/governance professional\n"
                        "- general professional\n\n"
                        f"CV:\n---\n{cv_text_truncated}\n---\n\n"
                        "Return a JSON object with exactly:\n"
                        "- category: one of the 5 strings above (exact match)\n"
                        "- reasoning: 2-3 sentences explaining the classification\n"
                        "- key_factors: array of 3-5 specific items from the CV supporting this"
                    ),
                }
            ],
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "category": {
                                "type": "string",
                                "enum": [
                                    "computer science student",
                                    "experienced ML professional",
                                    "professional with legal background",
                                    "policy/governance professional",
                                    "general professional",
                                ],
                            },
                            "reasoning": {"type": "string"},
                            "key_factors": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": ["category", "reasoning", "key_factors"],
                        "additionalProperties": False,
                    },
                }
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Claude API error: {e}")

    result = json.loads(response.content[0].text)
    return {
        "category": result["category"],
        "reasoning": result["reasoning"],
        "key_factors": result["key_factors"],
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
                "Your first characters must be a bold program name like **Program Name**."
            ),
            messages=[
                {
                    "role": "user",
                    "content": (
                        "## Background\n"
                        f"**Professional category:** {request.cv_category}\n"
                        f"**CV excerpt:** {request.cv_summary[:600]}\n\n"
                        "## Self-Assessment\n"
                        f"{answers_text}\n\n"
                        "## Available Programs\n"
                        f"{AI_SAFETY_PROGRAMS}\n\n"
                        "## Task\n"
                        "Recommend 3–5 programs. For each:\n"
                        "1. Bold the program name as a heading\n"
                        "2. Explain specifically WHY it fits me (reference my category, experience, time, and goals)\n"
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
                f"I was classified as: {request.cv_category}\n\n"
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
                "Always address the user as 'you'. Keep answers focused and practical."
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
