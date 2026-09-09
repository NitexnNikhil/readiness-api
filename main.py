from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional, Dict
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    KeepTogether
)
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
import os
import uuid


app = FastAPI(
    title="Candidate Readiness Report API",
    version="1.0.0"
)


# ============================================================
# MODELS
# ============================================================

class CandidateProfile(BaseModel):
    candidate_id: str
    name: str
    email: Optional[str] = ""
    phone: Optional[str] = ""
    location: Optional[str] = ""
    profile_summary: Optional[str] = ""


class Education(BaseModel):
    degree: str
    field_of_study: str
    institution: str
    academic_year: Optional[str] = ""
    graduation_year: Optional[str] = ""
    score: Optional[str] = ""
    score_type: Optional[str] = ""


class Evidence(BaseModel):
    source: str
    section: Optional[str] = ""
    evidence: str
    related_skill: Optional[str] = ""
    related_competency: Optional[str] = ""


class Skill(BaseModel):
    skill_id: str
    skill_name: str
    category: str
    evidence: List[str] = []


class Competency(BaseModel):
    competency_id: str
    competency_name: str
    evidence: List[str] = []
    score: Optional[float] = None
    level: Optional[str] = ""


class ReadinessDimension(BaseModel):
    score: Optional[float] = None
    level: Optional[str] = ""
    evidence: List[str] = []


class CommonIntelligence(BaseModel):
    candidate_profile: CandidateProfile
    education: List[Education]
    assessment: Dict
    evidence: List[Evidence]
    skills: List[Skill]
    competencies: List[Competency]
    scores: Dict
    readiness_dimensions: Dict[str, ReadinessDimension]
    overall_readiness: Dict


class Strength(BaseModel):
    area: str
    evidence: str
    summary: str


class DevelopmentArea(BaseModel):
    area: str
    reason: str
    priority: str


class GrowthArea(BaseModel):
    area: str
    reason: str
    current_state: str


class LearningRecommendation(BaseModel):
    recommendation: str
    reason: str
    related_area: str


class NextBestAction(BaseModel):
    action: str
    reason: str
    expected_outcome: str


class CandidateView(BaseModel):
    strengths: List[Strength]
    development_areas: List[DevelopmentArea]
    growth_area: GrowthArea
    learning_recommendations: List[LearningRecommendation]
    next_best_action: NextBestAction
    progress: Dict
    reassessment: Dict


class TPOView(BaseModel):
    placement_readiness: Dict
    role_fit: Dict
    hiring_gaps: List[Dict]
    placement_risks: List[Dict]
    success_gate: Dict
    recommendation: Dict


class RecruiterView(BaseModel):
    role_fit: Dict
    required_competencies: List[Dict]
    candidate_gaps: List[Dict]
    hiring_readiness: Dict
    success_gate: Dict
    recommendation: Dict


class PersonaSpecificIntelligence(BaseModel):
    candidate_view: CandidateView
    tpo_view: TPOView
    recruiter_employer_view: RecruiterView


class ReadinessPayload(BaseModel):
    common_intelligence: CommonIntelligence
    persona_specific_intelligence: PersonaSpecificIntelligence


# ============================================================
# PDF HELPERS
# ============================================================

PAGE_WIDTH, PAGE_HEIGHT = A4

MARGIN_LEFT = 16 * mm
MARGIN_RIGHT = 16 * mm
MARGIN_TOP = 15 * mm
MARGIN_BOTTOM = 15 * mm


def get_styles():
    styles = getSampleStyleSheet()

    return {
        "title": ParagraphStyle(
            "TitleCustom",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=27,
            leading=30,
            textColor=colors.HexColor("#063F2E"),
            spaceAfter=5
        ),

        "subtitle": ParagraphStyle(
            "Subtitle",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#555555")
        ),

        "section": ParagraphStyle(
            "Section",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=19,
            textColor=colors.HexColor("#063F2E"),
            spaceBefore=8,
            spaceAfter=7
        ),

        "small": ParagraphStyle(
            "Small",
            parent=styles["Normal"],
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#666666")
        ),

        "body": ParagraphStyle(
            "Body",
            parent=styles["Normal"],
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#333333")
        ),

        "body_bold": ParagraphStyle(
            "BodyBold",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#222222")
        ),

        "white_title": ParagraphStyle(
            "WhiteTitle",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=25,
            leading=28,
            textColor=colors.white
        ),

        "white_body": ParagraphStyle(
            "WhiteBody",
            parent=styles["Normal"],
            fontSize=9,
            leading=13,
            textColor=colors.white
        ),

        "score": ParagraphStyle(
            "Score",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=22,
            textColor=colors.HexColor("#00B887"),
            alignment=TA_CENTER
        )
    }


def score_level(score):
    if score is None:
        return "NOT ASSESSED"

    if score >= 4.5:
        return "ADVANCED"
    elif score >= 3.5:
        return "STRONG"
    elif score >= 3.0:
        return "PROFICIENT"
    elif score >= 2.0:
        return "DEVELOPING"
    else:
        return "EMERGING"


def readiness_status(score):
    if score is None:
        return "NOT ASSESSED"

    if score >= 3.5:
        return "READY"
    elif score >= 3.0:
        return "AT BAR"
    return "DEVELOPING"


def safe(value):
    if value is None:
        return ""
    return str(value)


# ============================================================
# PAGE HEADER / FOOTER
# ============================================================

def draw_header_footer(canvas, doc):
    canvas.saveState()

    # Header
    canvas.setFillColor(colors.HexColor("#063F2E"))
    canvas.rect(
        0,
        PAGE_HEIGHT - 8 * mm,
        PAGE_WIDTH,
        8 * mm,
        fill=1,
        stroke=0
    )

    canvas.setFillColor(colors.HexColor("#666666"))
    canvas.setFont("Helvetica", 7)

    canvas.drawString(
        MARGIN_LEFT,
        7 * mm,
        "HAVET AI · READINESS INTELLIGENCE"
    )

    canvas.drawRightString(
        PAGE_WIDTH - MARGIN_RIGHT,
        7 * mm,
        f"{doc.page:02d} / 02"
    )

    canvas.restoreState()


# ============================================================
# PDF GENERATION
# ============================================================

def generate_pdf(payload: ReadinessPayload):

    os.makedirs("output", exist_ok=True)

    filename = f"readiness_report_{uuid.uuid4().hex[:8]}.pdf"
    filepath = os.path.join("output", filename)

    styles = get_styles()

    doc = SimpleDocTemplate(
        filepath,
        pagesize=A4,
        rightMargin=MARGIN_RIGHT,
        leftMargin=MARGIN_LEFT,
        topMargin=20 * mm,
        bottomMargin=15 * mm
    )

    story = []

    common = payload.common_intelligence
    persona = payload.persona_specific_intelligence

    candidate = common.candidate_profile

    overall = common.overall_readiness

    overall_score = overall.get("score")
    overall_level = overall.get("level", score_level(overall_score))
    overall_summary = overall.get("summary", "")

    # ========================================================
    # PAGE 1
    # ========================================================

    story.append(
        Paragraph(
            "READINESS PROFILE",
            styles["small"]
        )
    )

    story.append(
        Paragraph(
            safe(candidate.name),
            styles["title"]
        )
    )

    education_text = ""

    if common.education:
        edu = common.education[0]

        education_text = (
            f"{safe(edu.field_of_study)} · "
            f"{safe(edu.academic_year)} · "
            f"{safe(edu.institution)} · "
            f"Class of {safe(edu.graduation_year)}"
        )

    story.append(
        Paragraph(
            education_text,
            styles["subtitle"]
        )
    )

    story.append(Spacer(1, 8))

    # Overall readiness box
    overall_data = [
        [
            Paragraph(
                "OVERALL READINESS",
                styles["small"]
            ),
            Paragraph(
                f"<b>{safe(overall_score)}</b> / 5.0",
                styles["score"]
            ),
            Paragraph(
                safe(overall_level),
                styles["body_bold"]
            )
        ]
    ]

    overall_table = Table(
        overall_data,
        colWidths=[55 * mm, 45 * mm, 55 * mm]
    )

    overall_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F7F4")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDE9E4")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (1, 0), (1, 0), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10)
        ])
    )

    story.append(overall_table)

    story.append(Spacer(1, 8))

    if overall_summary:
        story.append(
            Paragraph(
                safe(overall_summary),
                styles["body"]
            )
        )

    # ========================================================
    # READINESS DIMENSIONS
    # ========================================================

    dimension_rows = []

    for name, dimension in common.readiness_dimensions.items():

        score = dimension.score

        label = name.replace("_", " ").title()

        dimension_rows.append(
            [
                Paragraph(
                    safe(score),
                    styles["score"]
                ),
                Paragraph(
                    label,
                    styles["body_bold"]
                )
            ]
        )

    if dimension_rows:

        dimension_table = Table(
            [dimension_rows],
            colWidths=[
                31 * mm,
                31 * mm
            ] * len(dimension_rows)
        )

        dimension_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAF9")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E9E6")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8)
            ])
        )

        story.append(dimension_table)

    # ========================================================
    # SKILLS
    # ========================================================

    story.append(
        Paragraph(
            "01 Skills, scored on evidence",
            styles["section"]
        )
    )

    skill_data = [
        [
            Paragraph("<b>SKILL</b>", styles["small"]),
            Paragraph("<b>SCORE</b>", styles["small"]),
            Paragraph("<b>LEVEL</b>", styles["small"])
        ]
    ]

    for skill in common.skills:

        # Match competency score if available
        score = None
        level = ""

        for competency in common.competencies:
            if (
                competency.competency_id == skill.skill_id
                or competency.competency_name.lower()
                == skill.skill_name.lower()
            ):
                score = competency.score
                level = competency.level or score_level(score)
                break

        skill_data.append(
            [
                Paragraph(
                    safe(skill.skill_name),
                    styles["body_bold"]
                ),
                Paragraph(
                    safe(score),
                    styles["body"]
                ),
                Paragraph(
                    safe(level),
                    styles["small"]
                )
            ]
        )

    skill_table = Table(
        skill_data,
        colWidths=[
            90 * mm,
            25 * mm,
            35 * mm
        ],
        repeatRows=1
    )

    skill_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F3")),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E0E6E3")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6)
        ])
    )

    story.append(skill_table)

    # ========================================================
    # GROWTH AREA
    # ========================================================

    growth = persona.candidate_view.growth_area

    story.append(
        Paragraph(
            "02 What the candidate is building next",
            styles["section"]
        )
    )

    growth_data = [
        [
            Paragraph(
                "<b>ACTIVE GROWTH AREA</b>",
                styles["small"]
            ),
            Paragraph(
                "<b>REASON</b>",
                styles["small"]
            )
        ],
        [
            Paragraph(
                safe(growth.area),
                styles["body_bold"]
            ),
            Paragraph(
                safe(growth.reason),
                styles["body"]
            )
        ],
        [
            Paragraph(
                "<b>CURRENT STATE</b>",
                styles["small"]
            ),
            Paragraph(
                safe(growth.current_state),
                styles["body"]
            )
        ]
    ]

    growth_table = Table(
        growth_data,
        colWidths=[55 * mm, 95 * mm]
    )

    growth_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAF9")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDE7E2")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7)
        ])
    )

    story.append(growth_table)

    # ========================================================
    # PAGE 2
    # ========================================================

    story.append(PageBreak())

    story.append(
        Paragraph(
            "DECISION DETAIL",
            styles["small"]
        )
    )

    story.append(
        Paragraph(
            "Evidence, action,<br/>and gates.",
            styles["white_title"]
        )
    )

    story.append(Spacer(1, 10))

    # ========================================================
    # ROLE-SPECIFIC EVIDENCE
    # ========================================================

    story.append(
        Paragraph(
            "03 Role-specific evidence",
            styles["section"]
        )
    )

    evidence_data = [
        [
            Paragraph("<b>COMPETENCY</b>", styles["small"]),
            Paragraph("<b>SCORE</b>", styles["small"]),
            Paragraph("<b>READINESS</b>", styles["small"]),
            Paragraph("<b>EVIDENCE</b>", styles["small"]),
            Paragraph("<b>IMPLICATION</b>", styles["small"])
        ]
    ]

    for competency in common.competencies:

        evidence_text = "<br/>".join(
            [safe(x) for x in competency.evidence]
        )

        status = readiness_status(competency.score)

        evidence_data.append(
            [
                Paragraph(
                    safe(competency.competency_name),
                    styles["body_bold"]
                ),
                Paragraph(
                    safe(competency.score),
                    styles["body"]
                ),
                Paragraph(
                    status,
                    styles["small"]
                ),
                Paragraph(
                    evidence_text,
                    styles["small"]
                ),
                Paragraph(
                    "",
                    styles["small"]
                )
            ]
        )

    evidence_table = Table(
        evidence_data,
        colWidths=[
            38 * mm,
            16 * mm,
            23 * mm,
            48 * mm,
            30 * mm
        ],
        repeatRows=1
    )

    evidence_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F3")),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#DDE4E1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5)
        ])
    )

    story.append(evidence_table)

    # ========================================================
    # READINESS PATTERN
    # ========================================================

    story.append(
        Paragraph(
            "04 Readiness pattern",
            styles["section"]
        )
    )

    readiness_cards = []

    for name, dimension in common.readiness_dimensions.items():

        label = name.replace("_", " ").title()

        readiness_cards.append(
            [
                Paragraph(
                    safe(dimension.score),
                    styles["score"]
                ),
                Paragraph(
                    label,
                    styles["body_bold"]
                ),
                Paragraph(
                    safe(
                        dimension.level
                        or score_level(dimension.score)
                    ),
                    styles["small"]
                )
            ]
        )

    pattern_table = Table(
        [readiness_cards],
        colWidths=[32 * mm] * len(readiness_cards)
    )

    pattern_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAF9")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E1E8E4")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7)
        ])
    )

    story.append(pattern_table)

    # ========================================================
    # NEXT BEST ACTION
    # ========================================================

    story.append(
        Paragraph(
            "05 Next best action",
            styles["section"]
        )
    )

    action = persona.candidate_view.next_best_action

    action_data = [
        [
            Paragraph("<b>ACTION</b>", styles["small"]),
            Paragraph("<b>WHY</b>", styles["small"]),
            Paragraph("<b>EXPECTED OUTCOME</b>", styles["small"])
        ],
        [
            Paragraph(
                safe(action.action),
                styles["body_bold"]
            ),
            Paragraph(
                safe(action.reason),
                styles["body"]
            ),
            Paragraph(
                safe(action.expected_outcome),
                styles["body"]
            )
        ]
    ]

    action_table = Table(
        action_data,
        colWidths=[
            50 * mm,
            50 * mm,
            50 * mm
        ]
    )

    action_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F3")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDE5E1")),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E1E7E4")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7)
        ])
    )

    story.append(action_table)

    # ========================================================
    # SUCCESS GATE
    # ========================================================

    tpo_gate = persona.tpo_view.success_gate

    story.append(
        Spacer(1, 8)
    )

    story.append(
        Paragraph(
            "SUCCESS GATE",
            styles["small"]
        )
    )

    gate_text = (
        f"{safe(tpo_gate.get('competency'))} "
        f"≥ {safe(tpo_gate.get('minimum_score'))} / 5.0"
    )

    gate_table = Table(
        [
            [
                Paragraph(
                    gate_text,
                    styles["body_bold"]
                )
            ]
        ],
        colWidths=[150 * mm]
    )

    gate_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#063F2E")),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
            ("BOX", (0, 0), (-1, -1), 0, colors.white),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10)
        ])
    )

    story.append(gate_table)

    # ========================================================
    # FINAL DECISION
    # ========================================================

    story.append(
        Paragraph(
            "06 Final decision",
            styles["section"]
        )
    )

    recommendation = persona.tpo_view.recommendation

    decision = recommendation.get(
        "decision",
        ""
    )

    reason = recommendation.get(
        "reason",
        ""
    )

    decision_table = Table(
        [
            [
                Paragraph(
                    safe(decision),
                    styles["body_bold"]
                ),
                Paragraph(
                    safe(reason),
                    styles["body"]
                )
            ]
        ],
        colWidths=[65 * mm, 85 * mm]
    )

    decision_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#063F2E")),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10)
        ])
    )

    story.append(decision_table)

    # ========================================================
    # FOOTER INFORMATION
    # ========================================================

    story.append(Spacer(1, 10))

    assessment = common.assessment

    footer_data = [
        [
            Paragraph(
                "<b>EVIDENCE PROVENANCE</b><br/>"
                + ", ".join(
                    [
                        safe(x.source)
                        for x in common.evidence
                    ]
                ),
                styles["small"]
            ),
            Paragraph(
                "<b>ASSESSMENT</b><br/>"
                + safe(
                    assessment.get(
                        "assessment_date",
                        ""
                    )
                ),
                styles["small"]
            ),
            Paragraph(
                "<b>SOURCE</b><br/>"
                + safe(
                    assessment.get(
                        "source",
                        "resume"
                    )
                ),
                styles["small"]
            )
        ]
    ]

    footer_table = Table(
        footer_data,
        colWidths=[
            60 * mm,
            45 * mm,
            45 * mm
        ]
    )

    footer_table.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5)
        ])
    )

    story.append(footer_table)

    # ========================================================
    # BUILD
    # ========================================================

    doc.build(
        story,
        onFirstPage=draw_header_footer,
        onLaterPages=draw_header_footer
    )

    return filepath


# ============================================================
# API ENDPOINT
# ============================================================

@app.post("/generate-readiness-report")
def generate_readiness_report(payload: ReadinessPayload):

    pdf_path = generate_pdf(payload)

    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=os.path.basename(pdf_path)
    )


@app.get("/")
def root():

    return {
        "message": "Candidate Readiness Report API",
        "endpoint": "POST /generate-readiness-report"
    }