import re
from pathlib import Path

from arx_auditor.state import AuditState

# ---------------------------------------------------------------------------
# M13 — emit_findings + assemble_report
#
# Two thin plain-Python nodes. Neither belongs in graph control flow — they
# are deterministic renders with no branching, no accumulation, no pause.
# They sit at the end of the graph as cheap I/O steps.
#
# emit_findings  — one .md per approved verdict → out/<client>/findings/
# assemble_report — all .md files + HTML template → out/<client>/report.html
# ---------------------------------------------------------------------------

_SEVERITY_MAP = {
    "Fix": "High",
    "Suppress": "Informational",
    "Exception": "Medium",
    "Already-fixed": "Informational",
}

_FRAMEWORK_REFS = {
    "owasp": ("OWASP", "NIST 800-53: SI-10", "CIS: 18.1"),
    "cis":   ("CIS Benchmarks", "NIST 800-53: CM-6", "ISO 27001: A.12.6"),
    "cve":   ("CVE / NVD", "NIST 800-53: SI-2", "CIS: 7.3"),
}


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:48]


def _severity(bucket: str) -> str:
    return _SEVERITY_MAP.get(bucket, "Medium")


def _framework_lines(framework: str) -> str:
    primary, nist, cis_iso = _FRAMEWORK_REFS.get(framework.lower(), ("Unknown", "", ""))
    return f"- **Framework:** {primary}\n- **NIST:** {nist}\n- **Alt:** {cis_iso}"


def _render_md(n: int, verdict: dict, evidence: str) -> str:
    severity = _severity(verdict["bucket"])
    fw_lines = _framework_lines(verdict.get("framework", "owasp"))
    return (
        f"# {n:03d} — {verdict['title']}\n\n"
        f"**Severity:** {severity}  \n"
        f"**Bucket:** {verdict['bucket']}  \n"
        f"{fw_lines}\n\n"
        f"## Evidence\n\n{evidence}\n\n"
        f"## Classification\n\n{verdict['reason']}\n"
    )


def _build_html(client_id: str, findings_dir: Path) -> str:
    md_files = sorted(findings_dir.glob("*.md"))
    rows = []
    cards = []

    for md in md_files:
        text = md.read_text(encoding="utf-8")
        lines = text.splitlines()
        title = lines[0].lstrip("# ").strip() if lines else md.stem
        severity = next((l.split("**Severity:**")[-1].strip() for l in lines if "**Severity:**" in l), "")
        bucket = next((l.split("**Bucket:**")[-1].strip() for l in lines if "**Bucket:**" in l), "")
        slug = md.stem

        severity_color = {"High": "#f85149", "Medium": "#e3b341", "Informational": "#58a6ff"}.get(severity, "#9da7b3")
        bucket_color = {"Fix": "#f85149", "Suppress": "#58a6ff", "Exception": "#e3b341", "Already-fixed": "#3fb950"}.get(bucket, "#9da7b3")

        rows.append(
            f'<tr><td><a href="#{slug}">{title}</a></td>'
            f'<td style="color:{severity_color}">{severity}</td>'
            f'<td style="color:{bucket_color}">{bucket}</td></tr>'
        )

        body_html = "<br>".join(
            f"<strong>{l[3:]}</strong>" if l.startswith("## ") else l
            for l in lines[2:]
        )
        cards.append(f'<div class="finding" id="{slug}"><h2>{title}</h2>{body_html}</div>')

    table = (
        "<table><thead><tr><th>Finding</th><th>Severity</th><th>Bucket</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )
    body = "".join(cards)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Audit Report — {client_id}</title>
<style>
  body {{font-family: system-ui, sans-serif; background: #0d1117; color: #e6edf3;
         max-width: 900px; margin: 0 auto; padding: 2rem;}}
  h1 {{font-size: 1.6rem; margin-bottom: 1.5rem;}}
  h2 {{font-size: 1.1rem; color: #58a6ff; margin: 2rem 0 .5rem;}}
  table {{width: 100%; border-collapse: collapse; margin-bottom: 2.5rem;}}
  th {{text-align: left; border-bottom: 1px solid #30363d; padding: .5rem .75rem;
       color: #9da7b3; font-size: .82rem;}}
  td {{padding: .5rem .75rem; border-bottom: 1px solid #161b22; font-size: .88rem;}}
  td a {{color: #e6edf3; text-decoration: none;}}
  td a:hover {{color: #58a6ff;}}
  .finding {{background: #161b22; border: 1px solid #30363d; border-radius: 6px;
             padding: 1.25rem 1.5rem; margin-bottom: 1.25rem;}}
</style>
</head>
<body>
<h1>Audit Report — {client_id}</h1>
{table}
{body}
</body>
</html>"""


# ---------------------------------------------------------------------------
# LangGraph nodes
# ---------------------------------------------------------------------------


def emit_findings(state: AuditState) -> dict:
    """Write one .md per approved verdict to out/<client_id>/findings/."""
    client_id = state.get("client_id", "default")
    verdicts = state.get("final_verdicts") or state.get("verdicts", [])

    evidence_map = {f["id"]: f["evidence"] for f in state.get("findings", [])}

    out_dir = Path("out") / client_id / "findings"
    out_dir.mkdir(parents=True, exist_ok=True)

    for i, v in enumerate(verdicts, start=1):
        evidence = evidence_map.get(v["id"], "(no evidence recorded)")
        md = _render_md(i, v, evidence)
        fname = f"{i:03d}-{_slug(v['title'])}.md"
        (out_dir / fname).write_text(md, encoding="utf-8")

    return {}


def assemble_report(state: AuditState) -> dict:
    """Read all finding .md files, assemble into out/<client_id>/report.html."""
    client_id = state.get("client_id", "default")
    findings_dir = Path("out") / client_id / "findings"
    report_path = Path("out") / client_id / "report.html"

    report_path.parent.mkdir(parents=True, exist_ok=True)
    html = _build_html(client_id, findings_dir)
    report_path.write_text(html, encoding="utf-8")

    return {"report_path": str(report_path)}
