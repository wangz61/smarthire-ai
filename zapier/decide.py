"""Code by Zapier (Python) step: validate the judge's JSON and make the decision.

The LLM's verdict is advisory. The decision itself is a fixed rule applied in code, so it is
auditable and cannot be talked into by the resume:

    any mandatory requirement not "met"           -> reject
    else score >= pass_threshold                  -> advance
    else                                          -> reject
    judge output not valid JSON / wrong shape     -> needs_review (no email is sent)

score = 100 * mean(met = 1, partial = 0.5, not_met = 0) over all requirements, mandatory included.

Input Data (set these in the Zapier step):
    judge_output     the reply of the ChatGPT (OpenAI) step
    name, email      from the form
    title            job title, from the requirements step
    pass_threshold   from the requirements step
    company          optional, defaults to "SmartHire"

Output: decision, score, llm_score, llm_recommendation, mandatory_met, summary, strengths,
concerns (the judge's timeline note first, when it found the dates inconsistent), timeline_flag,
email_to, email_subject, email_body, evaluation_json.
"""
import json
import re

STATUS_POINTS = {"met": 1.0, "partial": 0.5, "not_met": 0.0}


class JudgeOutputError(ValueError):
    pass


def parse_judge(text):
    """The judge's reply -> dict. Tolerates ```json fences and text around the object."""
    text = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise JudgeOutputError("no JSON object in the judge output")
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError as e:
        raise JudgeOutputError(f"invalid JSON: {e}") from None
    validate(data)
    return data


def validate(data):
    for key in ("mandatory", "requirements"):
        items = data.get(key)
        if not isinstance(items, list):
            raise JudgeOutputError(f"'{key}' must be a list")
        for item in items:
            if not isinstance(item, dict) or item.get("status") not in STATUS_POINTS:
                raise JudgeOutputError(f"'{key}' entry has no valid status: {item!r}")
    if not data["mandatory"]:
        raise JudgeOutputError("'mandatory' is empty")
    score = data.get("overall_score")
    if not isinstance(score, (int, float)) or not 0 <= score <= 100:
        raise JudgeOutputError("'overall_score' must be a number from 0 to 100")


def timeline_concern(data):
    """The judge's timeline note when it found the dates inconsistent, else ''."""
    timeline = data.get("timeline")
    if isinstance(timeline, dict) and timeline.get("consistent") is False:
        return f"Timeline: {timeline.get('note') or 'dates do not add up'}"
    return ""


def score_of(data):
    items = data["mandatory"] + data["requirements"]
    return round(100 * sum(STATUS_POINTS[i["status"]] for i in items) / len(items))


def decide(data, threshold):
    mandatory_met = all(i["status"] == "met" for i in data["mandatory"])
    score = score_of(data)
    decision = "advance" if mandatory_met and score >= threshold else "reject"
    return decision, score, mandatory_met


def first_name(name):
    return (name or "").strip().split()[0] if (name or "").strip() else "there"


def email_for(decision, name, title, company, data):
    if decision == "advance":
        strengths = data.get("strengths") or []
        highlight = f" One highlight from your application: {strengths[0].rstrip('.')}." if strengths else ""
        return (f"Next steps for your {title} application at {company}",
                f"Hi {first_name(name)},\n\n"
                f"Thank you for applying for the {title} position at {company}. We have reviewed your "
                f"resume and would like to invite you to the next round of interviews.{highlight}\n\n"
                f"Our recruiting team will contact you within the next few days to schedule a call.\n\n"
                f"Best regards,\n{company} Recruiting Team")
    return (f"Your {title} application at {company}",
            f"Hi {first_name(name)},\n\n"
            f"Thank you for your interest in the {title} position at {company} and for the time you "
            f"spent on your application. After careful review, we have decided not to move forward "
            f"with your application for this role, as other candidates more closely match its "
            f"current requirements.\n\n"
            f"We appreciate your interest in {company} and wish you every success in your search.\n\n"
            f"Best regards,\n{company} Recruiting Team")


def main(data):
    threshold = float(data.get("pass_threshold") or 70)
    company = data.get("company") or "SmartHire"
    name, title = data.get("name", ""), data.get("title", "the")
    base = {"email_to": data.get("email", ""), "title": title, "name": name}
    try:
        judged = parse_judge(data.get("judge_output"))
    except JudgeOutputError as e:
        return {**base, "decision": "needs_review", "score": "", "llm_score": "", "llm_recommendation": "",
                "mandatory_met": "", "summary": f"Judge output could not be used: {e}",
                "strengths": "", "concerns": "", "timeline_flag": "", "email_subject": "", "email_body": "",
                "evaluation_json": ""}
    decision, score, mandatory_met = decide(judged, threshold)
    concerns = list(judged.get("concerns") or [])
    timeline = timeline_concern(judged)
    if timeline:
        concerns.insert(0, timeline)
    subject, body = email_for(decision, name, title, company, judged)
    return {
        **base,
        "decision": decision,
        "score": score,
        "llm_score": judged["overall_score"],
        "llm_recommendation": judged.get("recommendation", ""),
        "mandatory_met": mandatory_met,
        "summary": judged.get("summary", ""),
        "strengths": "\n".join(judged.get("strengths") or []),
        "concerns": "\n".join(concerns),
        "timeline_flag": bool(timeline),
        "email_subject": subject,
        "email_body": body,
        "evaluation_json": json.dumps(judged, ensure_ascii=False),
    }


# In Zapier, `input_data` is provided and `output` is read back. Locally, import main() instead.
# Read-only lookup: works whether Zapier runs this at module level or inside a function.
_zapier_input = globals().get("input_data") or locals().get("input_data")
if _zapier_input is not None:
    output = main(_zapier_input)
