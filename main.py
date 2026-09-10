from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Any, Dict
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
)
from reportlab.lib.units import inch
import os
from pathlib import Path
import html as html_lib
import shutil
import subprocess


app = FastAPI(
    title="Havet AI Readiness Report",
    version="1.0"
)

templates = Jinja2Templates(directory="templates")


# ---------------------------------------------------------
# Request model
# ---------------------------------------------------------

class ReadinessPayload(BaseModel):
    common_intelligence: Dict[str, Any]
    persona_specific_intelligence: Dict[str, Any]


# ---------------------------------------------------------
# Helper functions
# ---------------------------------------------------------

def get_level(score):

    if score is None:
        return "NOT ASSESSED"

    if score >= 4.5:
        return "ADVANCED"

    if score >= 3.5:
        return "STRONG"

    if score >= 3.0:
        return "PROFICIENT"

    if score >= 2.0:
        return "DEVELOPING"

    return "EMERGING"


def get_readiness(score):

    if score is None:
        return "NOT ASSESSED"

    if score >= 3.5:
        return "READY"

    if score >= 3.0:
        return "AT BAR"

    return "DEVELOPING"


def fmt_score(value):
    if value is None:
        return "N/A"

    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)

    text = f"{number:.2f}".rstrip("0").rstrip(".")
    return text or "0"


def join_nonempty(parts, separator=" · "):
    cleaned = [str(part).strip() for part in parts if part not in (None, "")]
    return separator.join(cleaned)


def short_display_name(full_name):
    if not full_name:
        return "Candidate"

    parts = str(full_name).split()
    if len(parts) == 1:
        return parts[0]

    first_name = parts[0]
    last_initial = parts[-1][0].upper() + "."
    return f"{first_name} {last_initial}"


def pick_communication_dimension(common: Dict[str, Any], dimensions: Dict[str, Any]) -> Dict[str, Any]:
    """
    Prefer the explicit communication block, but gracefully fall back to
    any legacy or alternate nesting used by the payload.
    """
    candidates = [
        common.get("communication"),
        dimensions.get("communication"),
        common.get("readiness_dimensions", {}).get("communication"),
        common.get("scores", {}).get("communication"),
    ]

    for candidate in candidates:
        if isinstance(candidate, dict) and candidate:
            return candidate

    return {}


def find_browser_executable():
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
    ]

    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate

    return None


def build_display_context(context):
    candidate = context["candidate"]
    education = context["education"]
    assessment = context["assessment"]
    competencies = context["competencies"]
    dimensions = context["dimensions"]
    overall = context["overall"]
    scores = context.get("scores", {})
    candidate_view = context["candidate_view"]
    tpo_view = context["tpo_view"]

    assessment_date = assessment.get("assessment_date") or "N/A"
    assessment_source = str(assessment.get("source") or assessment.get("assessment_type") or "assessment")
    assessment_source_label = assessment_source.replace("_", " ").upper()
    percentile = scores.get("percentile")
    cohort_comparison = scores.get("cohort_comparison")
    skills_count = scores.get("skills_count")
    sources_count = scores.get("sources_count")
    if skills_count is None:
        skills_count = len(competencies)
    skills_count_text = f"{int(skills_count)} SKILLS" if isinstance(skills_count, (int, float)) else f"{skills_count} SKILLS"

    def ordinal_suffix(value: int) -> str:
        if 10 <= value % 100 <= 20:
            return "TH"
        if value % 10 == 1:
            return "ST"
        if value % 10 == 2:
            return "ND"
        if value % 10 == 3:
            return "RD"
        return "TH"

    tag_parts = []
    if isinstance(percentile, (int, float)):
        percentile_int = int(percentile)
        tag_parts.append(f"{percentile_int}{ordinal_suffix(percentile_int)} PERCENTILE")
    elif assessment_source_label:
        tag_parts.append(assessment_source_label)

    if isinstance(cohort_comparison, (int, float)):
        sign = "+" if cohort_comparison >= 0 else ""
        tag_parts.append(f"{sign}{cohort_comparison:g} VS COHORT")

    tag_parts.append(skills_count_text)

    if sources_count is not None:
        sources_count_text = f"{int(sources_count)} SOURCES" if isinstance(sources_count, (int, float)) else f"{sources_count} SOURCES"
        tag_parts.append(sources_count_text)
    elif assessment_date and assessment_date != "N/A":
        tag_parts.append(assessment_date)

    skills_tag = " · ".join(tag_parts)

    profile_bits = []
    if education:
        edu = education[0]
        profile_bits.extend(
            [
                edu.get("field_of_study"),
                edu.get("academic_year"),
                edu.get("institution"),
                f"Class of {edu.get('graduation_year')}" if edu.get("graduation_year") else None,
            ]
        )
    else:
        profile_bits.append(candidate.get("profile_summary"))

    profile_line = join_nonempty(profile_bits)
    if not profile_line:
        profile_line = "Profile information unavailable"

    overall_level = overall.get("level") or get_level(overall.get("score"))
    overall_summary = overall.get("summary") or candidate.get("profile_summary") or "Readiness summary unavailable."
    overall_score_text = fmt_score(overall.get("score"))

    communication_dimension = context.get("communication") or {}
    summary_dimensions = [
        {
            "label": "Learning agility",
            "score_text": fmt_score(dimensions.get("learning_agility", {}).get("score")),
            "level": dimensions.get("learning_agility", {}).get("level") or get_level(dimensions.get("learning_agility", {}).get("score")),
        },
        {
            "label": "Communication",
            "score_text": fmt_score(communication_dimension.get("score")),
            "level": communication_dimension.get("level") or get_level(communication_dimension.get("score")),
        },
        {
            "label": "Technical depth",
            "score_text": fmt_score(dimensions.get("technical_fundamentals", {}).get("score")),
            "level": dimensions.get("technical_fundamentals", {}).get("level") or get_level(dimensions.get("technical_fundamentals", {}).get("score")),
        },
        {
            "label": "Project readiness",
            "score_text": fmt_score(dimensions.get("project_readiness", {}).get("score")),
            "level": dimensions.get("project_readiness", {}).get("level") or get_level(dimensions.get("project_readiness", {}).get("score")),
        },
    ]

    pattern_dimension_keys = [
        ("technical_fundamentals", "Technical fundamentals"),
        ("project_readiness", "Project readiness"),
        ("learning_agility", "Learning agility"),
        ("communication", "Communication"),
        ("role_fit", "Role fit"),
    ]
    pattern_dimensions = []
    for key, label in pattern_dimension_keys:
        if key == "communication":
            dimension = context.get("communication") or dimensions.get(key, {})
        else:
            dimension = dimensions.get(key, {})
        pattern_dimensions.append(
            {
                "label": label,
                "score_text": fmt_score(dimension.get("score")),
                "level": dimension.get("level") or get_level(dimension.get("score")),
            }
        )

    recruiter_view = context.get("recruiter_view", {})
    candidate_gap_map = {
        item.get("competency"): item
        for item in recruiter_view.get("candidate_gaps", [])
        if item.get("competency")
    }

    skills = []
    evidence_rows = []
    for item in competencies:
        competency_name = item.get("competency_name", "")
        score_text = fmt_score(item.get("score"))
        level_text = item.get("level") or get_level(item.get("score"))
        readiness_text = get_readiness(item.get("score"))
        evidence_text = join_nonempty(item.get("evidence", []), "; ") or "No evidence listed."
        gap = candidate_gap_map.get(competency_name, {})
        implication_text = (
            item.get("implication")
            or gap.get("impact")
            or gap.get("gap")
            or "Supporting signal for the report."
        )

        skills.append(
            {
                "name": competency_name,
                "score_text": score_text,
                "level": level_text,
            }
        )
        evidence_rows.append(
            {
                "name": competency_name,
                "score_text": score_text,
                "readiness_text": readiness_text,
                "readiness_class": "at-bar" if readiness_text == "AT BAR" else "",
                "evidence_text": evidence_text,
                "implication_text": implication_text,
            }
        )

    growth_area = candidate_view.get("growth_area", {})
    next_best_action = candidate_view.get("next_best_action", {})
    reassessment = candidate_view.get("reassessment", {})
    recommendation = tpo_view.get("recommendation", {})
    success_gate = tpo_view.get("success_gate", {})

    threshold_score = success_gate.get("minimum_score")
    if threshold_score is None:
        threshold_score = 3.0

    threshold_pass_count = 0
    for item in competencies:
        score = item.get("score")
        if isinstance(score, (int, float)) and score >= threshold_score:
            threshold_pass_count += 1

    gate_required = bool(success_gate.get("required"))
    gate_competency = success_gate.get("competency") or "SUCCESS GATE"
    if not gate_required:
        gate_title = "NOT REQUIRED"
        gate_threshold = "Not applicable"
    else:
        gate_title = gate_competency
        gate_threshold = f"≥ {fmt_score(threshold_score)} / 5.0"

    action_cards = [
        {
            "kind": "action",
            "tag": "NOW",
            "title": next_best_action.get("action") or growth_area.get("area") or "Immediate action",
            "body": next_best_action.get("reason") or growth_area.get("reason") or "Focus on the highest-leverage improvement first.",
        },
        {
            "kind": "action",
            "tag": "WHY",
            "title": growth_area.get("area") or "Current growth area",
            "body": growth_area.get("current_state") or growth_area.get("reason") or "Current evidence is limited in this area.",
        },
        {
            "kind": "action",
            "tag": "EXPECTED OUTCOME",
            "title": next_best_action.get("expected_outcome") or "Expected outcome",
            "body": recommendation.get("reason") or "A stronger, more defensible readiness signal.",
        },
        {
            "kind": "gate",
            "tag": "SUCCESS GATE",
            "title": gate_title,
            "threshold": gate_threshold,
        },
    ]

    decision_headline = recommendation.get("decision") or tpo_view.get("hiring_readiness", {}).get("level") or "Decision unavailable"
    decision_subtitle = recommendation.get("reason") or overall_summary

    evidence_provenance = join_nonempty(
        [
            assessment_source_label,
            assessment_date,
            candidate.get("candidate_id"),
        ]
    )
    if not evidence_provenance:
        evidence_provenance = "Assessment provenance unavailable"

    reassessment_due = (
        reassessment.get("due_date")
        or assessment.get("reassessment_due")
        or "TBD"
    )

    growth_score = growth_area.get("score")
    growth_score_text = f"{fmt_score(growth_score)} / 5" if growth_score is not None else None

    return {
        "display_name": short_display_name(candidate.get("name", "Candidate")),
        "candidate_id": candidate.get("candidate_id", ""),
        "profile_line": profile_line,
        "overall_score_text": overall_score_text,
        "scale_max_text": f"{float(overall.get('scale_max') or 5.0):.1f}",
        "overall_level": overall_level,
        "overall_summary": overall_summary,
        "skills_tag": skills_tag,
        "skills": skills,
        "summary_dimensions": summary_dimensions,
        "pattern_dimensions": pattern_dimensions,
        "growth_title": join_nonempty([growth_area.get("area"), growth_score_text]),
        "growth_body": ". ".join(
            part.rstrip(".")
            for part in [
                growth_area.get("current_state"),
                growth_area.get("reason"),
            ]
            if part
        ),
        "reassessment_due": reassessment_due,
        "decision_intro": "Supporting detail for the recommendation on page 1: what was observed, what it means, and what should happen next.",
        "threshold_score_text": f"{float(threshold_score):.1f} / 5.0",
        "threshold_summary_text": f"{threshold_pass_count} of {len(competencies)} at or above threshold",
        "evidence_rows": evidence_rows,
        "action_cards": action_cards,
        "decision_headline": decision_headline,
        "decision_subtitle": decision_subtitle,
        "evidence_provenance": evidence_provenance,
        "footer_assessed": join_nonempty([assessment_date, assessment_source_label]),
        "source_record": candidate.get("candidate_id", ""),
    }


def build_browser_pdf(html_path: str, output_path: str) -> None:
    browser = find_browser_executable()
    if not browser:
        raise FileNotFoundError("Google Chrome or Chromium was not found")

    html_url = Path(html_path).resolve().as_uri()
    command = [
        browser,
        "--headless",
        "--disable-gpu",
        "--allow-file-access-from-files",
        "--run-all-compositor-stages-before-draw",
        "--print-to-pdf-no-header",
        "--no-pdf-header-footer",
        f"--print-to-pdf={output_path}",
        html_url,
    ]

    subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )


def build_fallback_pdf(output_path: str, context: dict) -> None:
    """
    Generate a basic PDF report when WeasyPrint is unavailable.

    This keeps the endpoint functional on machines that do not have the
    native GTK/Pango libraries required by WeasyPrint.
    """
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=0.5 * inch,
        leftMargin=0.5 * inch,
        topMargin=3.85 * inch,
        bottomMargin=0.5 * inch,
    )

    story = []
    title_style = styles["Title"]
    body_style = styles["BodyText"]
    heading_style = styles["Heading2"]
    small_style = styles["BodyText"]
    small_style.fontSize = 8
    small_style.leading = 10

    dark = colors.HexColor("#0b4a37")
    mint = colors.HexColor("#39d49a")
    text_dark = colors.HexColor("#15352d")
    muted = colors.HexColor("#60736c")
    line = colors.HexColor("#dbe5e0")

    candidate = context["candidate"]
    overall = context["overall"]
    competencies = context["competencies"]
    dimensions = context["dimensions"]
    candidate_view = context["candidate_view"]
    tpo_view = context["tpo_view"]
    assessment = context["assessment"]
    education = context["education"]
    growth = candidate_view.get("growth_area", {})
    recommendation = tpo_view.get("recommendation", {})
    gate = tpo_view.get("success_gate", {})

    def fmt_score(value):
        return "N/A" if value is None else f"{value:.1f}" if isinstance(value, (int, float)) else str(value)

    def safe_text(value, default=""):
        return default if value is None else str(value)

    def wrap_text(text, width, font="Helvetica", size=8):
        words = str(text).split()
        lines = []
        current = ""
        for word in words:
            test = f"{current} {word}".strip()
            if stringWidth(test, font, size) <= width or not current:
                current = test
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines

    def draw_header(canvas, page_num, total_pages, title, subtitle=""):
        canvas.saveState()
        canvas.setFillColor(dark)
        canvas.rect(0, 592, 595, 248, stroke=0, fill=1)
        canvas.setFillColor(mint)
        canvas.roundRect(44, 778, 18, 18, 4, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 14)
        canvas.drawString(70, 784, "havet AI")
        canvas.setFillColor(colors.HexColor("#a7c2bb"))
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(551, 784, f"{title} · {page_num:02d} / {total_pages:02d}")
        canvas.setFillColor(colors.HexColor("#76cdb0"))
        canvas.setFont("Helvetica", 8)
        canvas.drawString(44, 742, subtitle)
        canvas.restoreState()

    def draw_footer(canvas, left_text, right_text):
        canvas.saveState()
        canvas.setStrokeColor(line)
        canvas.line(44, 48, 551, 48)
        canvas.setFillColor(colors.HexColor("#7b8e87"))
        canvas.setFont("Helvetica", 6.5)
        canvas.drawString(44, 34, left_text)
        canvas.drawRightString(551, 34, right_text)
        canvas.restoreState()

    def page_one(canvas, doc):
        draw_header(
            canvas,
            1,
            2,
            "CANDIDATE READINESS REPORT",
            "READINESS PROFILE",
        )
        draw_footer(
            canvas,
            "HAVET AI  •  READINESS INTELLIGENCE",
            f"ASSESSED {assessment.get('assessment_date', '')}  •  PROFILE {candidate.get('candidate_id', '')}",
        )

    def page_two(canvas, doc):
        draw_header(
            canvas,
            2,
            2,
            candidate.get("name", ""),
            "DECISION DETAIL",
        )
        draw_footer(
            canvas,
            "EVIDENCE PROVENANCE",
            f"SOURCE RECORDS  •  {candidate.get('candidate_id', '')}",
        )

    story.append(Paragraph("READINESS PROFILE", small_style))
    story.append(Paragraph(f"<font size=28><b>{html_lib.escape(candidate.get('name', 'Candidate'))}</b></font>", title_style))

    if education:
        edu = education[0]
        meta = " · ".join(filter(None, [
            safe_text(edu.get("field_of_study")),
            safe_text(edu.get("academic_year")),
            safe_text(edu.get("institution")),
            f"Class of {edu.get('graduation_year')}" if edu.get("graduation_year") else None,
        ]))
        story.append(Paragraph(html_lib.escape(meta), body_style))
    story.append(Spacer(1, 0.14 * inch))
    story.append(Paragraph(html_lib.escape(safe_text(overall.get("summary", ""))), body_style))

    # Overall readiness box
    score_data = [
        [
            Paragraph("<font color='#6a8078' size=7>OVERALL READINESS</font>", body_style),
            Paragraph(f"<font color='#15b07d' size=26><b>{fmt_score(overall.get('score'))}</b></font> <font color='#657b73' size=12>/ 5.0</font>", body_style),
            Paragraph(f"<font color='#15352d' size=12><b>{html_lib.escape(overall.get('level', ''))}</b></font>", body_style),
        ]
    ]
    score_table = Table(score_data, colWidths=[180, 120, 120], rowHeights=[60])
    score_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), dark),
        ("BOX", (0, 0), (-1, -1), 0, dark),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
    ]))
    story.append(Spacer(1, 0.15 * inch))
    story.append(score_table)

    dim_cells = []
    for key, dimension in list(dimensions.items())[:4]:
        dim_cells.append(Paragraph(
            f"<font size=18 color='#15b07d'><b>{fmt_score(dimension.get('score'))}</b></font><br/>"
            f"<font size=8 color='#15352d'><b>{html_lib.escape(key.replace('_', ' ').title())}</b></font>",
            body_style,
        ))
    while len(dim_cells) < 4:
        dim_cells.append("")
    dim_table = Table([dim_cells], colWidths=[130, 130, 130, 130])
    dim_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("LINEABOVE", (0, 0), (-1, -1), 1, line),
        ("LINEBELOW", (0, 0), (-1, -1), 1, line),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(Spacer(1, 0.15 * inch))
    story.append(dim_table)
    story.append(Spacer(1, 0.2 * inch))

    story.append(Paragraph("01  Skills, scored on evidence", heading_style))
    story.append(Spacer(1, 0.07 * inch))
    skill_rows = [[
        Paragraph("<font size=7 color='#6a7f78'>SKILL</font>", body_style),
        Paragraph("<font size=7 color='#6a7f78'>SCORE</font>", body_style),
        Paragraph("<font size=7 color='#6a7f78'>LEVEL</font>", body_style),
    ]]
    for item in competencies:
        skill_rows.append([
            Paragraph(f"<b>{html_lib.escape(safe_text(item.get('competency_name', '')))}</b>", body_style),
            Paragraph(f"<font color='#15b07d'><b>{fmt_score(item.get('score'))}</b></font>", body_style),
            Paragraph(html_lib.escape(safe_text(item.get("level", ""))), body_style),
        ])
    skill_table = Table(skill_rows, colWidths=[290, 90, 130], repeatRows=1)
    skill_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f4f7f6")),
        ("BOX", (0, 0), (-1, -1), 1, line),
        ("INNERGRID", (0, 0), (-1, -1), 1, line),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(skill_table)

    story.append(PageBreak())
    story.append(Paragraph("DECISION DETAIL", small_style))
    story.append(Paragraph("<font size=24><b>Evidence, action, and gates.</b></font>", title_style))
    story.append(Spacer(1, 0.08 * inch))
    story.append(Paragraph("Supporting detail for the recommendation on page 1: what was observed, what it means, and what should happen next.", body_style))
    story.append(Spacer(1, 0.06 * inch))

    growth_lines = wrap_text(growth.get("current_state", "") or growth.get("reason", ""), 260, size=7)
    growth_table = Table([[
        Paragraph(
            f"<font size=6.5 color='#4d8975'><b>02  WHAT SHE IS BUILDING NEXT</b></font><br/>"
            f"<font size=12 color='#15352d'><b>{html_lib.escape(safe_text(growth.get('area', 'Not identified')))}</b></font><br/>"
            f"<font size=7 color='#4e6059'>{html_lib.escape(' '.join(growth_lines))}</font>",
            body_style,
        ),
        Paragraph(
            f"<font size=6.5 color='#4d8975'><b>RE-ASSESSMENT DUE</b></font><br/>"
            f"<font size=11 color='#15352d'><b>{html_lib.escape(safe_text(candidate_view.get('reassessment', {}).get('due_date'), 'Dec 2026'))}</b></font><br/>"
            f"<font size=7 color='#4e6059'>Scores are a point in time, not a fixed label.</font>",
            body_style,
        )
    ]], colWidths=[355, 185])
    growth_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f7f9f8")),
        ("BOX", (0, 0), (-1, -1), 1, line),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(growth_table)
    story.append(Spacer(1, 0.05 * inch))

    story.append(Paragraph("<font size=13><b>03  Role-specific evidence</b></font>", body_style))
    evidence_rows = [[
        Paragraph("<font size=5.5 color='#6a7f78'>COMPETENCY</font>", body_style),
        Paragraph("<font size=5.5 color='#6a7f78'>SCORE</font>", body_style),
        Paragraph("<font size=5.5 color='#6a7f78'>READINESS</font>", body_style),
        Paragraph("<font size=5.5 color='#6a7f78'>EVIDENCE</font>", body_style),
        Paragraph("<font size=5.5 color='#6a7f78'>IMPLICATION</font>", body_style),
    ]]
    for item in competencies:
        evidence_rows.append([
            Paragraph(f"<b>{html_lib.escape(safe_text(item.get('competency_name', '')))}</b>", body_style),
            Paragraph(f"<font color='#15b07d'><b>{fmt_score(item.get('score'))}</b></font>", body_style),
            Paragraph(html_lib.escape(safe_text(item.get("readiness", ""))), body_style),
            Paragraph(html_lib.escape("; ".join(item.get("evidence", []))), body_style),
            Paragraph(html_lib.escape(safe_text(item.get("implication", "Supporting signal for the report."))), body_style),
        ])
    evidence_table = Table(evidence_rows, colWidths=[120, 42, 58, 165, 117], repeatRows=1)
    evidence_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f4f7f6")),
        ("BOX", (0, 0), (-1, -1), 1, line),
        ("INNERGRID", (0, 0), (-1, -1), 1, line),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(evidence_table)
    story.append(Spacer(1, 0.08 * inch))

    story.append(Paragraph("<font size=13><b>04  Readiness pattern</b></font>", body_style))
    pattern_cells = []
    for key, dimension in dimensions.items():
        pattern_cells.append(Paragraph(
            f"<font size=15 color='#15b07d'><b>{fmt_score(dimension.get('score'))}</b></font><br/>"
            f"<font size=6.5><b>{html_lib.escape(key.replace('_', ' ').title())}</b></font><br/>"
            f"<font size=5.5 color='#6a7f78'>{html_lib.escape(dimension.get('level', ''))}</font>",
            body_style,
        ))
    if pattern_cells:
        pattern_table = Table([pattern_cells], colWidths=[112] * len(pattern_cells))
        pattern_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f7f9f8")),
            ("BOX", (0, 0), (-1, -1), 1, line),
            ("INNERGRID", (0, 0), (-1, -1), 1, line),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(pattern_table)
    story.append(Spacer(1, 0.14 * inch))

    story.append(Spacer(1, 0.04 * inch))
    story.append(Paragraph("<font size=13><b>05  Next best action</b></font>", body_style))
    action = candidate_view.get("next_best_action", {})
    action_table = Table([[
        Paragraph(
            f"<font size=6 color='#4d8975'><b>NOW</b></font><br/>"
            f"<font size=8.5 color='#15352d'><b>{html_lib.escape(safe_text(action.get('action', growth.get('area', 'Close the design gap'))))}</b></font>",
            body_style,
        ),
        Paragraph(
            f"<font size=6 color='#4d8975'><b>WHY</b></font><br/>"
            f"<font size=6.5 color='#4e6059'>{html_lib.escape(safe_text(action.get('reason', growth.get('reason', 'Focus on the highest leverage improvement first.'))))}</font>",
            body_style,
        ),
        Paragraph(
            f"<font size=6 color='#4d8975'><b>EXPECTED OUTCOME</b></font><br/>"
            f"<font size=6.5 color='#4e6059'>{html_lib.escape(safe_text(action.get('expected_outcome', 'A stronger, more defensible readiness signal.')))}</font>",
            body_style,
        ),
        Paragraph(
            f"<font size=6 color='#76cdb0'><b>SUCCESS GATE</b></font><br/>"
            f"<font size=8.5 color='#ffffff'><b>{html_lib.escape(safe_text(gate.get('competency', growth.get('area', 'OOP & Design'))))} >= {fmt_score(gate.get('minimum_score', 3.0))} / 5.0</b></font>",
            body_style,
        ),
    ]], colWidths=[132, 132, 132, 126])
    action_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (2, 0), colors.HexColor("#f7f9f8")),
        ("BACKGROUND", (3, 0), (3, 0), dark),
        ("BOX", (0, 0), (-1, -1), 1, line),
        ("INNERGRID", (0, 0), (-1, -1), 1, line),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(action_table)
    story.append(Spacer(1, 0.01 * inch))
    story.append(Paragraph("<font size=13><b>06  Final decision</b></font>", body_style))
    story.append(Paragraph(
        f"<font size=8.5 color='#15352d'><b>{html_lib.escape(safe_text(recommendation.get('decision', 'Shortlist now; unlock higher-bar opportunities after the design gate.')))}</b></font><br/>"
        f"<font size=6.5 color='#4e6059'>{html_lib.escape(safe_text(recommendation.get('reason', 'This is contextual decision support, not a permanent label or guarantee.')))}</font>",
        body_style,
    ))
    story.append(Spacer(1, 0.03 * inch))

    doc.build(story, onFirstPage=page_one, onLaterPages=page_two)


# ---------------------------------------------------------
# Generate PDF
# ---------------------------------------------------------

@app.post("/generate-readiness-report")
async def generate_readiness_report(
    payload: ReadinessPayload
):
    common = payload.common_intelligence
    persona = payload.persona_specific_intelligence

    candidate = common.get(
        "candidate_profile",
        {}
    )

    education = common.get(
        "education",
        []
    )

    assessment = common.get(
        "assessment",
        {}
    )

    competencies = common.get(
        "competencies",
        []
    )

    dimensions = common.get(
        "readiness_dimensions",
        {}
    )

    overall = common.get(
        "overall_readiness",
        {}
    )

    communication = pick_communication_dimension(common, dimensions)

    candidate_view = persona.get(
        "candidate_view",
        {}
    )

    tpo_view = persona.get(
        "tpo_view",
        {}
    )

    # -----------------------------------------------------
    # Prepare derived display values
    # -----------------------------------------------------

    overall_score = overall.get("score")

    if not overall.get("level"):
        overall["level"] = get_level(
            overall_score
        )

    for competency in competencies:

        score = competency.get("score")

        if not competency.get("level"):
            competency["level"] = get_level(score)

        competency["readiness"] = get_readiness(
            score
        )

    for key, dimension in dimensions.items():

        if not dimension.get("level"):

            dimension["level"] = get_level(
                dimension.get("score")
            )

    # -----------------------------------------------------
    # Template context
    # -----------------------------------------------------

    context = {
        "candidate": candidate,
        "education": education,
        "assessment": assessment,
        "competencies": competencies,
        "scores": common.get("scores", {}),
        "dimensions": dimensions,
        "overall": overall,
        "candidate_view": candidate_view,
        "tpo_view": tpo_view,
        "recruiter_view": persona.get("recruiter_employer_view", {}),
        "communication": communication,
        "common_threshold": 3.0,
    }

    display_context = build_display_context(
        context
    )

    # -----------------------------------------------------
    # Render HTML
    # -----------------------------------------------------

    html_content = templates.get_template(
        "readiness_report.html"
    ).render(**display_context)

    # -----------------------------------------------------
    # Create output directory
    # -----------------------------------------------------

    os.makedirs(
        "output",
        exist_ok=True
    )

    html_filename = "readiness_report.html"
    filename = "readiness_report.pdf"

    html_path = os.path.join(
        "output",
        html_filename
    )

    output_path = os.path.join(
        "output",
        filename
    )

    with open(html_path, "w", encoding="utf-8") as html_file:
        html_file.write(html_content)

    # -----------------------------------------------------
    # HTML → PDF
    # -----------------------------------------------------

    try:
        build_browser_pdf(
            html_path=html_path,
            output_path=output_path,
        )
    except Exception:
        build_fallback_pdf(
            output_path=output_path,
            context=context
        )

    return FileResponse(
        output_path,
        media_type="application/pdf",
        filename=filename
    )


@app.get("/")
def root():

    return {
        "message": "Havet AI Readiness Report API",
        "endpoint": "POST /generate-readiness-report"
    }
