import json
import xml.etree.ElementTree as ET
from pathlib import Path

from arx_auditor.state import AuditState, Finding

_NESSUS_NS = {"cm": "http://www.nessus.org/cm"}

# ---------------------------------------------------------------------------
# Plain Python — testable without LangGraph
# ---------------------------------------------------------------------------

def load_burp(path: str | Path) -> list[Finding]:
    """Parse a Burp Suite JSON issue export into Finding dicts."""
    with open(path) as fh:
        raw = json.load(fh)

    issues = raw.get("issues", raw) if isinstance(raw, dict) else raw

    findings: list[Finding] = []
    for idx, issue in enumerate(issues, start=1):
        host = issue.get("host", "")
        path_ = issue.get("path", issue.get("url", ""))
        severity = issue.get("severity", issue.get("risk", "Unknown"))
        findings.append(
            Finding(
                id=f"B-{idx:03d}",
                source="burp",
                title=issue.get("name", issue.get("issueName", f"Burp finding {idx}")),
                evidence=f"{host}{path_} — {severity}",
                framework="owasp",
                control_id="",  # filled by router (M5)
            )
        )
    return findings


def parse_nessus(path: str | Path) -> list[Finding]:
    """Parse a .nessus XML file into Finding dicts.

    Skips severity-0 (informational) items.
    Compliance-check items (cm:compliance-check-name present) are routed to
    the CIS framework; all others go to CVE.
    """
    tree = ET.parse(path)
    root = tree.getroot()
    findings: list[Finding] = []
    idx = 1

    for host in root.iter("ReportHost"):
        host_name = host.get("name", "")
        for item in host.iter("ReportItem"):
            severity = int(item.get("severity", "0"))
            if severity == 0:
                continue

            plugin_name = item.get("pluginName", f"Plugin {item.get('pluginID', '?')}")
            port = item.get("port", "")
            proto = item.get("protocol", "tcp")
            cve = item.findtext("cve") or ""
            compliance_name = (
                item.findtext("cm:compliance-check-name", namespaces=_NESSUS_NS) or ""
            )

            framework = "cis" if compliance_name else "cve"
            evidence_parts = [f"{host_name}:{port}/{proto}", f"severity {severity}"]
            if cve:
                evidence_parts.append(cve)

            findings.append(
                Finding(
                    id=f"N-{idx:03d}",
                    source="nessus",
                    title=plugin_name,
                    evidence=" — ".join(evidence_parts),
                    framework=framework,
                    control_id="",  # filled by router (M5)
                )
            )
            idx += 1

    return findings


def dedupe(findings: list[Finding]) -> list[Finding]:
    """Remove duplicate findings. Two findings are duplicates when they share
    the same normalised title and source scanner — same plugin, same tool.
    First occurrence wins; later copies are dropped.
    """
    seen: set[tuple[str, str]] = set()
    out: list[Finding] = []
    for f in findings:
        key = (f["title"].strip().lower(), f["source"])
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out


# ---------------------------------------------------------------------------
# Thin node wrappers — sit in the graph only to order their writes into state
# ---------------------------------------------------------------------------

_DEFAULT_BURP = Path("data/samples/burp.json")
_DEFAULT_NESSUS = Path("data/samples/scan.nessus")


def parse_scans(state: AuditState) -> dict:
    """Node: read scanner files and populate findings."""
    findings = load_burp(_DEFAULT_BURP) + parse_nessus(_DEFAULT_NESSUS)
    return {"findings": findings}


def normalize(state: AuditState) -> dict:
    """Node: deduplicate findings from parse_scans."""
    return {"findings": dedupe(state["findings"])}
