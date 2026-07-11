"""Render personalized Haru action-plan PDF (agent brief, not a full dictionary)."""
from __future__ import annotations

import io
from typing import Any, Dict

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

from action_plan_builder import build_action_plan_content
from roadmap_engine import normalize_lang
from backend_i18n import t

_FONT_REGISTERED = False
FONT_BY_LANG = {"zh-TW": "MSung-Light", "ja": "HeiseiMin-W3", "en": "Helvetica"}


def _ensure_fonts():
    global _FONT_REGISTERED
    if _FONT_REGISTERED:
        return
    for name in ("MSung-Light", "HeiseiMin-W3"):
        try:
            pdfmetrics.registerFont(UnicodeCIDFont(name))
        except Exception:
            pass
    _FONT_REGISTERED = True


def _font(lang: str) -> str:
    return FONT_BY_LANG.get(normalize_lang(lang), "MSung-Light")


def _draw_wrapped(c, text, x, y, max_w, lh, font, size, page_h) -> float:
    if not text:
        return y
    c.setFont(font, size)
    for paragraph in text.replace("\r", "").split("\n"):
        if not paragraph.strip():
            y -= lh * 0.4
            continue
        line = ""
        for ch in paragraph:
            trial = line + ch
            if c.stringWidth(trial, font, size) <= max_w:
                line = trial
            else:
                if y < 28 * mm:
                    c.showPage()
                    y = page_h - 22 * mm
                    c.setFont(font, size)
                c.drawString(x, y, line)
                y -= lh
                line = ch
        if line:
            if y < 28 * mm:
                c.showPage()
                y = page_h - 22 * mm
                c.setFont(font, size)
            c.drawString(x, y, line)
            y -= lh
    return y


def _section(c, title, y, margin, font, page_h) -> float:
    if y < 35 * mm:
        c.showPage()
        y = page_h - 22 * mm
    c.setFont(font, 13)
    c.drawString(margin, y, title)
    return y - 8 * mm


def build_action_plan_pdf(plan: Dict[str, Any]) -> bytes:
    _ensure_fonts()
    lang = plan.get("lang", "zh-TW")
    font = _font(lang)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, page_h = A4
    margin = 20 * mm
    cw = w - 2 * margin
    y = page_h - 22 * mm

    c.setFont(font, 20)
    c.drawString(margin, y, t("pdfTitle", lang))
    y -= 9 * mm

    school_name = plan["school_info"].get("school_name") or ("你" if lang == "zh-TW" else ("you" if lang == "en" else "あなた"))
    sub = t("pdfSubFor", lang, name=school_name, date=plan["generated_at"])
    if plan.get("ai_generated"):
        sub += t("pdfAiTag", lang)
    c.setFont(font, 9)
    y = _draw_wrapped(c, sub, margin, y, cw, 4.5 * mm, font, 9, page_h)
    y -= 6 * mm

    # Haru greeting
    y = _section(c, t("pdfSectionGreeting", lang), y, margin, font, page_h)
    y = _draw_wrapped(c, plan.get("greeting", ""), margin, y, cw, 5 * mm, font, 10, page_h)
    y -= 3 * mm
    if plan.get("agent_message"):
        y = _draw_wrapped(c, plan["agent_message"], margin, y, cw, 5 * mm, font, 10, page_h)
    y -= 6 * mm

    if plan.get("all_done"):
        y = _draw_wrapped(c, t("pdfAllDone", lang), margin, y, cw, 5 * mm, font, 11, page_h)
    else:
        focus = plan.get("focus") or {}

        # NOW — primary focus
        y = _section(c, t("pdfSectionNow", lang), y, margin, font, page_h)
        c.setFont(font, 14)
        y = _draw_wrapped(c, focus.get("title", ""), margin, y, cw, 6 * mm, font, 14, page_h)

        meta_parts = []
        if focus.get("phase"):
            meta_parts.append(focus["phase"])
        if focus.get("duration_min"):
            meta_parts.append(t("pdfDuration", lang, n=focus["duration_min"]))
        if focus.get("deadline_days"):
            meta_parts.append(t("pdfDeadline", lang, n=focus["deadline_days"]))
        if meta_parts:
            c.setFont(font, 9)
            y = _draw_wrapped(c, " · ".join(meta_parts), margin, y, cw, 4 * mm, font, 9, page_h)

        if focus.get("summary"):
            y -= 2 * mm
            y = _draw_wrapped(c, focus["summary"], margin, y, cw, 5 * mm, font, 10, page_h)

        if plan.get("agent_where"):
            y -= 2 * mm
            y = _draw_wrapped(c, t("pdfWhereTo", lang) + plan["agent_where"], margin, y, cw, 5 * mm, font, 10, page_h)

        # Steps checklist
        y -= 3 * mm
        y = _section(c, t("pdfSectionSteps", lang), y, margin, font, page_h)
        for i, step in enumerate(plan.get("steps") or [], 1):
            y = _draw_wrapped(c, f"[ ] {i}. {step}", margin + 2 * mm, y, cw - 2 * mm, 5 * mm, font, 10, page_h)

        if focus.get("documents"):
            y -= 2 * mm
            y = _draw_wrapped(c, t("pdfBring", lang) + "、".join(focus["documents"]), margin, y, cw, 5 * mm, font, 10, page_h)

        if focus.get("tips"):
            y -= 2 * mm
            for tip in focus["tips"][:4]:
                y = _draw_wrapped(c, f"Tip: {tip}", margin + 2 * mm, y, cw - 2 * mm, 4.5 * mm, font, 9, page_h)

        links = focus.get("official_links") or []
        if links:
            y -= 2 * mm
            y = _section(c, t("pdfSectionOfficial", lang), y, margin, font, page_h)
            for link in links[:3]:
                y = _draw_wrapped(c, f"• {link.get('label', '')}", margin + 2 * mm, y, cw - 2 * mm, 4.5 * mm, font, 9, page_h)
                y = _draw_wrapped(c, f"  {link.get('url', '')}", margin + 4 * mm, y, cw - 4 * mm, 4 * mm, font, 8, page_h)

        # Next after this
        upcoming = plan.get("upcoming") or []
        if upcoming:
            y -= 4 * mm
            y = _section(c, t("pdfSectionNext", lang), y, margin, font, page_h)
            for i, u in enumerate(upcoming, 1):
                line = f"{i}. {u.get('title', '')}"
                y = _draw_wrapped(c, line, margin, y, cw, 5 * mm, font, 10, page_h)
                if u.get("summary"):
                    y = _draw_wrapped(c, f"   {u['summary']}", margin + 4 * mm, y, cw - 4 * mm, 4.5 * mm, font, 9, page_h)

    # Completed wins
    done = plan.get("completed_milestones") or []
    if done:
        y -= 4 * mm
        y = _section(c, t("pdfSectionMilestones", lang), y, margin, font, page_h)
        for task_title in done:
            y = _draw_wrapped(c, f"[x] {task_title}", margin + 2 * mm, y, cw - 2 * mm, 4.5 * mm, font, 9, page_h)

    # Compact path ahead (titles only, no full dump)
    path = plan.get("path_ahead") or []
    if path and not plan.get("all_done"):
        y -= 4 * mm
        y = _section(c, t("pdfSectionPath", lang), y, margin, font, page_h)
        c.setFont(font, 8)
        y = _draw_wrapped(c, t("pdfPathIntro", lang), margin, y, cw, 4 * mm, font, 8, page_h)
        y -= 2 * mm
        for block in path:
            if y < 30 * mm:
                c.showPage()
                y = page_h - 22 * mm
            c.setFont(font, 9)
            y = _draw_wrapped(c, f"— {block.get('phase', '')}", margin, y, cw, 4.5 * mm, font, 9, page_h)
            for task in block.get("tasks", []):
                mark = "○" if task.get("state") == "available" else "·"
                y = _draw_wrapped(c, f"  {mark} {task.get('title', '')}", margin, y, cw, 4 * mm, font, 8, page_h)

    c.setFont(font, 7)
    c.drawString(margin, 12 * mm, t("pdfFooter", lang))

    c.save()
    buf.seek(0)
    return buf.read()


def build_roadmap_pdf(
    roadmap_data: Dict[str, Any],
    school_info: Dict[str, Any],
    lang: str = "zh-TW",
    current_address: str = "",
) -> bytes:
    """Build personalized action-plan PDF (replaces full roadmap dictionary export)."""
    plan = build_action_plan_content(roadmap_data, school_info, lang, current_address)
    return build_action_plan_pdf(plan)
