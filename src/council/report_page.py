"""Build the self-contained, read-only `report.html` from an existing `run.json`.

This is a separate step from `council run` (T16): it reads a run folder's
`run.json` and writes `report.html` into that same folder. No server, no build
step, no external dependency - one file, vanilla JS, opens by double-click.

The only data the page trusts to be safe markup is the two `<script>` blocks
this module writes itself. Everything from the run - case text, claim text,
narrative, judge notes, and so on - is embedded as JSON data and rendered by
the page's own script using `textContent`/`createTextNode` only, never
`innerHTML`, so it can never execute as HTML no matter what it contains.
"""

import html
import json
from pathlib import Path
import types
import typing

from pydantic import BaseModel

from council.models import RunBundle

REPORT_FILENAME = "report.html"


def _prune_unknown_fields(model_cls: type[BaseModel], data: object) -> object:
    """Drop dict keys that are not fields of `model_cls`, recursing into nested
    models/lists/dicts, so a `run.json` written under an earlier version of the
    data contracts (with fields since removed, e.g. a retired `Scorecard`
    field) can still be read back for display.

    This only prunes extra keys; it never invents a field the old file is
    missing, so a file that is genuinely incompatible (a required field
    actually absent, or a value of the wrong shape) still fails validation
    exactly as it would without this step. This function is used only by
    `write_report_page`'s read of an already-produced `run.json` - every other
    contract model (specialist/judge/chair drafts, and any other model in
    `council.models`) still parses with the same `extra="forbid"` strictness
    it always has; nothing here changes that."""
    if not isinstance(data, dict):
        return data
    pruned: dict[str, object] = {}
    for name, field in model_cls.model_fields.items():
        if name not in data:
            continue
        pruned[name] = _prune_value(field.annotation, data[name])
    return pruned


def _prune_value(annotation: object, value: object) -> object:
    origin = typing.get_origin(annotation)
    if origin is typing.Union or origin is types.UnionType:
        for arg in typing.get_args(annotation):
            if isinstance(arg, type) and issubclass(arg, BaseModel) and isinstance(value, dict):
                return _prune_unknown_fields(arg, value)
        return value
    if origin is list:
        (item_type,) = typing.get_args(annotation)
        return ([_prune_value(item_type, item) for item in value]
                if isinstance(value, list) else value)
    if origin is dict:
        _, value_type = typing.get_args(annotation)
        return ({key: _prune_value(value_type, item) for key, item in value.items()}
                if isinstance(value, dict) else value)
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return _prune_unknown_fields(annotation, value)
    return value


def _escape_json_for_script(data: object) -> str:
    """Serialize as JSON and neutralize `</` so the payload cannot prematurely
    close the `<script>` element that holds it (the only injection risk for
    data sitting inside a script tag - the browser does not parse a script
    element's contents as markup otherwise)."""
    raw = json.dumps(data, ensure_ascii=False)
    return raw.replace("</", "<\\/")


def render_report_html(bundle: RunBundle) -> str:
    """Render the full report page for one run bundle."""
    data_json = _escape_json_for_script(bundle.model_dump(mode="json"))
    title = html.escape(bundle.run_id, quote=True)
    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        f"<title>Council report: {title}</title>\n"
        f"<style>{_CSS}</style>\n</head>\n<body>\n"
        '<div id="app"></div>\n'
        '<aside id="panel" aria-hidden="true">\n'
        '  <div id="panel-inner">\n'
        '    <button type="button" id="panel-close" aria-label="Close">&times;</button>\n'
        '    <div id="panel-body"></div>\n'
        "  </div>\n"
        "</aside>\n"
        f'<script id="council-run-data" type="application/json">{data_json}</script>\n'
        f"<script>{_JS}</script>\n"
        "</body>\n</html>\n"
    )


def write_report_page(run_folder: Path) -> Path:
    """Read `run.json` from `run_folder` and write `report.html` next to it.

    Tolerates and ignores unknown fields left over from an older schema
    version (see `_prune_unknown_fields`) - this is reading our own,
    already-validated historical output back for display, not validating
    fresh model output."""
    run_json_path = run_folder / "run.json"
    raw = json.loads(run_json_path.read_text(encoding="utf-8"))
    bundle = RunBundle.model_validate(_prune_unknown_fields(RunBundle, raw))
    output_path = run_folder / REPORT_FILENAME
    output_path.write_text(render_report_html(bundle), encoding="utf-8")
    return output_path


_CSS = """
:root {
  color-scheme: light;
  --bg: #f7f7f5; --panel-bg: #ffffff; --ink: #1c1c1c; --muted: #5b5b5b;
  --line: #d9d9d4; --accent: #1f5fa8; --warn-bg: #fff3cd; --warn-ink: #5a4200;
  --ok: #1e6b3c; --bad: #a3272a; --chip-bg: #eef1f6;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font: 15px/1.5 -apple-system, Segoe UI, Helvetica, Arial, sans-serif;
}
#app { max-width: 900px; margin: 0 auto; padding: 16px 20px 80px; }
h1 { font-size: 1.4em; margin: 0.2em 0; }
h2 { font-size: 1.1em; border-bottom: 1px solid var(--line); padding-bottom: 4px; }
h3 { font-size: 0.98em; color: var(--muted); }
section { margin: 22px 0; }
.disclaimer {
  background: var(--warn-bg); color: var(--warn-ink); border: 1px solid #e4c876;
  padding: 8px 14px; font-weight: 600; position: sticky; top: 0; z-index: 5;
}
.status-line { color: var(--muted); }
.warning { background: var(--warn-bg); color: var(--warn-ink); padding: 6px 10px; border-radius: 4px; }
.privacy-line { color: var(--muted); font-size: 0.92em; }
.narrative { white-space: pre-wrap; }
.meta { color: var(--muted); font-size: 0.92em; }
.badge {
  display: inline-block; background: var(--chip-bg); border-radius: 4px;
  padding: 2px 8px; font-size: 0.85em;
}
.badge.grounded, .verified { color: var(--ok); }
.badge.ungrounded, .unverified { color: var(--bad); }
.badge.level-high { background: #e3f3e8; } .badge.level-medium { background: #fdf3d8; }
.badge.level-low { background: #fbe4e4; }
.flag { font-size: 0.85em; }
.quote { font-style: italic; }
table { border-collapse: collapse; width: 100%; font-size: 0.92em; }
th, td { border: 1px solid var(--line); padding: 4px 8px; text-align: left; }
ul { padding-left: 20px; }
dl { display: grid; grid-template-columns: max-content 1fr; gap: 2px 10px; }
dt { color: var(--muted); }
button.id-link {
  background: var(--chip-bg); border: 1px solid var(--line); border-radius: 4px;
  padding: 1px 6px; font: inherit; cursor: pointer; color: var(--accent);
}
button.id-link:hover { background: #dfe6f2; }
mark { background: #fff3a3; }
#panel {
  position: fixed; top: 0; right: 0; height: 100%; width: min(420px, 92vw);
  background: var(--panel-bg); border-left: 1px solid var(--line);
  transform: translateX(100%); transition: transform 0.15s ease-out;
  overflow-y: auto; z-index: 10; box-shadow: -2px 0 10px rgba(0,0,0,0.08);
}
#panel.open { transform: translateX(0); }
#panel-inner { padding: 16px 18px 40px; }
#panel-close {
  float: right; font-size: 1.3em; background: none; border: none; cursor: pointer;
  line-height: 1;
}
#panel-body p, #panel-body li { word-wrap: break-word; }
""".strip()


_JS = r"""
(function () {
  "use strict";
  var bundle = JSON.parse(document.getElementById("council-run-data").textContent);
  var report = bundle.report;
  var app = document.getElementById("app");
  var panelEl = document.getElementById("panel");
  var panelBody = document.getElementById("panel-body");

  function el(tag, opts) {
    var e = document.createElement(tag);
    opts = opts || {};
    if (opts["class"]) { e.className = opts["class"]; }
    if (opts.text !== undefined && opts.text !== null) { e.textContent = String(opts.text); }
    return e;
  }

  // ---- Build an index of every clickable ID in the run --------------------
  var sourceIndex = {};
  function registerSource(id, sourceType, title, text, flagged, flagReasons) {
    sourceIndex[id] = {
      sourceType: sourceType, title: title, text: text,
      flagged: !!flagged, flagReasons: flagReasons || [],
    };
  }
  (bundle.case_context.sections || []).forEach(function (s) {
    registerSource(s.id, "case", s.heading, s.text, s.flagged, s.flag_reasons);
  });
  Object.keys(bundle.sources || {}).forEach(function (id) {
    if (sourceIndex[id]) { return; }
    var s = bundle.sources[id];
    registerSource(id, s.source_type, s.source_title, s.text);
  });

  var claimIndex = {};
  var argumentIndex = {};
  (bundle.arguments || []).forEach(function (a) {
    argumentIndex[a.argument_id] = a;
    (a.claims || []).forEach(function (c) {
      claimIndex[c.claim_id] = { claim: c, argumentId: a.argument_id };
    });
    if (a.rebuttal) {
      (a.rebuttal.response_claims || []).forEach(function (c) {
        claimIndex[c.claim_id] = { claim: c, argumentId: a.argument_id, isRebuttal: true };
      });
    }
  });

  var findings = report.red_team_findings || [];
  var findingIndex = {};
  findings.forEach(function (f) { findingIndex[f.finding_id] = f; });

  function idKind(id) {
    if (claimIndex[id]) { return "claim"; }
    if (argumentIndex[id]) { return "argument"; }
    if (findingIndex[id]) { return "finding"; }
    if (sourceIndex[id]) { return "source"; }
    return null;
  }

  var allIds = Object.keys(claimIndex).concat(
    Object.keys(argumentIndex), Object.keys(findingIndex), Object.keys(sourceIndex));
  allIds = Array.prototype.filter.call(
    allIds.filter(function (v, i) { return allIds.indexOf(v) === i; }),
    function (id) { return id.length > 0; }
  );
  allIds.sort(function (a, b) { return b.length - a.length; });
  function escapeRegExp(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }
  var idPattern = allIds.length
    ? new RegExp("(" + allIds.map(escapeRegExp).join("|") + ")", "g")
    : null;

  function idButton(id) {
    var kind = idKind(id);
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "id-link id-" + (kind || "unknown");
    btn.textContent = id;
    btn.addEventListener("click", function () { openPanel(id); });
    return btn;
  }

  // Splits `text` on every known ID and appends plain text nodes for the
  // surrounding text and buttons for the IDs - text is never turned into
  // HTML at any point.
  function linkify(container, text) {
    if (text === undefined || text === null || text === "") { return; }
    text = String(text);
    if (!idPattern) { container.appendChild(document.createTextNode(text)); return; }
    var parts = text.split(idPattern);
    parts.forEach(function (part) {
      if (part === "") { return; }
      if (idKind(part)) { container.appendChild(idButton(part)); }
      else { container.appendChild(document.createTextNode(part)); }
    });
  }

  function idList(labelText, ids) {
    var p = el("p");
    p.appendChild(document.createTextNode(labelText + ": "));
    if (!ids || !ids.length) { p.appendChild(document.createTextNode("none")); return p; }
    ids.forEach(function (id, i) {
      if (i) { p.appendChild(document.createTextNode(", ")); }
      p.appendChild(idButton(id));
    });
    return p;
  }

  function judgeNotesForClaim(claimId) {
    var notes = [];
    (bundle.scorecard.scores || []).forEach(function (score) {
      (score.feedback || []).forEach(function (fb) {
        if (fb.claim_id === claimId) {
          notes.push({ judge: score.judge, kind: "feedback", text: fb.note });
        }
      });
      (score.untraceable_claims || []).forEach(function (u) {
        if (u.claim_id === claimId) {
          notes.push({ judge: score.judge, kind: "untraceable", text: u.reason });
        }
      });
    });
    return notes;
  }

  // ---- Highlighting a passage's cited words, without innerHTML ------------
  function appendHighlighted(container, text, quotes) {
    var ranges = [];
    quotes.forEach(function (quote) {
      var lowerText = text.toLowerCase();
      var searchFrom = 0;
      String(quote).split("...").map(function (p) { return p.trim(); })
        .filter(Boolean).forEach(function (part) {
          var idx = lowerText.indexOf(part.toLowerCase(), searchFrom);
          if (idx !== -1) { ranges.push([idx, idx + part.length]); searchFrom = idx + part.length; }
        });
    });
    ranges.sort(function (a, b) { return a[0] - b[0]; });
    var merged = [];
    ranges.forEach(function (r) {
      var last = merged[merged.length - 1];
      if (last && r[0] <= last[1]) { last[1] = Math.max(last[1], r[1]); }
      else { merged.push(r.slice()); }
    });
    var pos = 0;
    merged.forEach(function (r) {
      if (r[0] > pos) { container.appendChild(document.createTextNode(text.slice(pos, r[0]))); }
      var mark = document.createElement("mark");
      mark.textContent = text.slice(r[0], r[1]);
      container.appendChild(mark);
      pos = r[1];
    });
    container.appendChild(document.createTextNode(text.slice(pos)));
  }

  // ---- Panels ---------------------------------------------------------------
  function renderClaimPanel(id) {
    var entry = claimIndex[id];
    var claim = entry.claim;
    var wrap = el("div");
    wrap.appendChild(el("h2", { text: "Claim " + id }));
    var argLine = el("p", { "class": "meta" });
    argLine.appendChild(document.createTextNode("From argument "));
    argLine.appendChild(idButton(entry.argumentId));
    wrap.appendChild(argLine);
    wrap.appendChild(el("p", { text: claim.text }));
    wrap.appendChild(el("p", { "class": "badge " + claim.grounding_status, text: claim.grounding_status }));
    wrap.appendChild(el("h3", { text: "Citations" }));
    var ul = el("ul");
    (claim.citations || []).forEach(function (c) {
      var li = el("li", { "class": c.verified ? "verified" : "unverified" });
      li.appendChild(idButton(c.passage_id));
      var quote = el("span", { "class": "quote" });
      quote.textContent = ' "' + c.quote + '"';
      li.appendChild(quote);
      var flag = el("span", { "class": "flag" });
      flag.textContent = c.verified ? " verified" : " NOT VERIFIED" + (c.verify_note ? ": " + c.verify_note : "");
      li.appendChild(flag);
      ul.appendChild(li);
    });
    if (!claim.citations || !claim.citations.length) { ul.appendChild(el("li", { text: "None" })); }
    wrap.appendChild(ul);
    var notes = judgeNotesForClaim(id);
    if (notes.length) {
      wrap.appendChild(el("h3", { text: "Judge notes" }));
      var nul = el("ul");
      notes.forEach(function (n) {
        nul.appendChild(el("li", { text: "[" + n.judge + "] " + n.kind + ": " + n.text }));
      });
      wrap.appendChild(nul);
    }
    var mentioning = findings.filter(function (f) {
      return (f.evidence_ids || []).indexOf(id) !== -1;
    });
    if (mentioning.length) {
      wrap.appendChild(el("h3", { text: "Red-team findings mentioning this claim" }));
      var ful = el("ul");
      mentioning.forEach(function (f) {
        var li = el("li");
        li.appendChild(idButton(f.finding_id));
        ful.appendChild(li);
      });
      wrap.appendChild(ful);
    }
    return wrap;
  }

  function renderArgumentPanel(id) {
    var a = argumentIndex[id];
    var wrap = el("div");
    wrap.appendChild(el("h2", { text: "Argument " + id + " (" + a.role + ", Round " + a.round + ")" }));
    wrap.appendChild(el("p", { "class": "badge", text: "status: " + a.status }));
    if (a.status === "failed") {
      wrap.appendChild(el("p", { "class": "warning", text: "Failure reason: " + a.failure_reason }));
      return wrap;
    }
    var stanceLine = "Stance: " + a.stance + (a.stance_changed ? " (changed from Round 1)" : "");
    wrap.appendChild(el("p", { "class": "meta", text: stanceLine }));
    wrap.appendChild(el("p", { text: a.summary }));
    if (a.conditions && a.conditions.length) {
      wrap.appendChild(el("h3", { text: "Conditions" }));
      var cul = el("ul");
      a.conditions.forEach(function (c) { cul.appendChild(el("li", { text: c })); });
      wrap.appendChild(cul);
    }
    if (a.uncertainties && a.uncertainties.length) {
      wrap.appendChild(el("h3", { text: "Uncertainties" }));
      var uul = el("ul");
      a.uncertainties.forEach(function (c) { uul.appendChild(el("li", { text: c })); });
      wrap.appendChild(uul);
    }
    wrap.appendChild(el("h3", { text: "Claims" }));
    var claimsUl = el("ul");
    (a.claims || []).forEach(function (c) {
      var li = el("li");
      li.appendChild(idButton(c.claim_id));
      li.appendChild(document.createTextNode(" — " + c.text));
      claimsUl.appendChild(li);
    });
    wrap.appendChild(claimsUl);
    if (a.rebuttal) {
      wrap.appendChild(el("h3", { text: "Rebuttal" }));
      var rp = el("p");
      rp.appendChild(document.createTextNode("Targets "));
      rp.appendChild(idButton(a.rebuttal.target_claim_id));
      rp.appendChild(document.createTextNode(" in "));
      rp.appendChild(idButton(a.rebuttal.target_argument_id));
      wrap.appendChild(rp);
      wrap.appendChild(el("p", { "class": "meta", text: a.rebuttal.why_strongest }));
      wrap.appendChild(el("h4", { text: "Response claims" }));
      var rul = el("ul");
      (a.rebuttal.response_claims || []).forEach(function (c) {
        var li = el("li");
        li.appendChild(idButton(c.claim_id));
        li.appendChild(document.createTextNode(" — " + c.text));
        rul.appendChild(li);
      });
      wrap.appendChild(rul);
    }
    if (a.revisions && a.revisions.length) {
      wrap.appendChild(el("h3", { text: "Round 1 to Round 2 revisions" }));
      var revUl = el("ul");
      a.revisions.forEach(function (r) {
        var li = el("li");
        li.appendChild(idButton(r.round1_claim_id));
        li.appendChild(document.createTextNode(" — " + r.action));
        if (r.new_claim_id) {
          li.appendChild(document.createTextNode(" → "));
          li.appendChild(idButton(r.new_claim_id));
        }
        li.appendChild(el("div", { "class": "meta", text: r.reason }));
        revUl.appendChild(li);
      });
      wrap.appendChild(revUl);
    }
    return wrap;
  }

  function renderSourcePanel(id) {
    var s = sourceIndex[id];
    var wrap = el("div");
    var label = s.sourceType === "case" ? "Case section " : "KB passage ";
    wrap.appendChild(el("h2", { text: label + id }));
    wrap.appendChild(el("p", { "class": "meta", text: s.title }));
    if (s.flagged) {
      var reasons = s.flagReasons.length ? " (" + s.flagReasons.join(", ") + ")" : "";
      wrap.appendChild(el("p", { "class": "warning", text: "Flagged: possible instruction" + reasons }));
    }
    var citing = [];
    Object.keys(claimIndex).forEach(function (cid) {
      (claimIndex[cid].claim.citations || []).forEach(function (c) {
        if (c.passage_id === id) { citing.push({ claimId: cid, quote: c.quote, verified: c.verified }); }
      });
    });
    var body = el("p");
    appendHighlighted(body, s.text, citing.map(function (c) { return c.quote; }));
    wrap.appendChild(body);
    if (citing.length) {
      wrap.appendChild(el("h3", { text: "Cited by" }));
      var ul = el("ul");
      citing.forEach(function (c) {
        var li = el("li", { "class": c.verified ? "verified" : "unverified" });
        li.appendChild(idButton(c.claimId));
        var q = el("span", { "class": "quote" });
        q.textContent = ' "' + c.quote + '"';
        li.appendChild(q);
        ul.appendChild(li);
      });
      wrap.appendChild(ul);
    }
    return wrap;
  }

  function renderFindingPanel(id) {
    var f = findingIndex[id];
    var wrap = el("div");
    wrap.appendChild(el("h2", { text: "Finding " + id }));
    wrap.appendChild(el("p", { "class": "badge", text: f.severity + " / " + f.category }));
    wrap.appendChild(el("p", { text: f.description }));
    wrap.appendChild(el("h3", { text: "Evidence" }));
    var ul = el("ul");
    (f.evidence_ids || []).forEach(function (eid) {
      var li = el("li");
      li.appendChild(idButton(eid));
      ul.appendChild(li);
    });
    if (!f.evidence_ids || !f.evidence_ids.length) { ul.appendChild(el("li", { text: "None" })); }
    wrap.appendChild(ul);
    wrap.appendChild(el("h3", { text: "Suggested action" }));
    wrap.appendChild(el("p", { text: f.suggested_action }));
    if (f.affected_roles && f.affected_roles.length) {
      wrap.appendChild(el("p", { "class": "meta", text: "Affects: " + f.affected_roles.join(", ") }));
    }
    return wrap;
  }

  function renderConfidencePanel() {
    var c = report.confidence;
    var wrap = el("div");
    wrap.appendChild(el("h2", { text: "Confidence" }));
    wrap.appendChild(el("p", { text: c.level + " — " + c.score.toFixed(1) + " / 100" }));
    var dl = el("dl");
    Object.keys(c.inputs).forEach(function (k) {
      dl.appendChild(el("dt", { text: k }));
      dl.appendChild(el("dd", { text: JSON.stringify(c.inputs[k]) }));
    });
    wrap.appendChild(dl);
    return wrap;
  }

  function openPanel(id) {
    while (panelBody.firstChild) { panelBody.removeChild(panelBody.firstChild); }
    var kind = idKind(id);
    var content;
    if (kind === "claim") { content = renderClaimPanel(id); }
    else if (kind === "argument") { content = renderArgumentPanel(id); }
    else if (kind === "source") { content = renderSourcePanel(id); }
    else if (kind === "finding") { content = renderFindingPanel(id); }
    else { content = el("p", { text: "Unknown id: " + id }); }
    panelBody.appendChild(content);
    panelEl.className = "open";
    panelEl.setAttribute("aria-hidden", "false");
  }
  document.getElementById("panel-close").addEventListener("click", function () {
    panelEl.className = "";
    panelEl.setAttribute("aria-hidden", "true");
  });

  // ---- Page body --------------------------------------------------------
  function section(titleText) {
    var s = el("section");
    s.appendChild(el("h2", { text: titleText }));
    return s;
  }

  app.appendChild(el("div", { "class": "disclaimer", text: report.disclaimer }));

  var header = el("div");
  header.appendChild(el("h1", { text: "Council report: " + bundle.run_id }));
  var statusText = "Case " + bundle.case_id + " — status " + report.status +
    (report.recommendation ? " — recommendation: " + report.recommendation : " — no recommendation");
  header.appendChild(el("p", { "class": "status-line", text: statusText }));
  if (report.council_warning) {
    header.appendChild(el("p", { "class": "warning", text: report.council_warning }));
  }
  if (report.incomplete_reasons && report.incomplete_reasons.length) {
    header.appendChild(el("p", { "class": "warning", text: "Incomplete: " + report.incomplete_reasons.join("; ") }));
  }
  app.appendChild(header);

  var priv = report.privacy_summary;
  var privText = "Privacy: marker " + (priv.synthetic_marker_found ? "found" : "MISSING") +
    ", ingest identifier hits: " + priv.ingest_identifier_hits +
    ", outbound prompts checked: " + priv.outbound_prompts_checked +
    ", blocked: " + priv.outbound_prompts_blocked +
    ", providers used: " + (priv.providers_used.join(", ") || "none");
  app.appendChild(el("p", { "class": "privacy-line", text: privText }));

  if (report.confidence) {
    var confSec = section("Confidence");
    var confBtn = el("button", {
      "class": "badge level-" + report.confidence.level,
      text: report.confidence.level + " (" + report.confidence.score.toFixed(1) + " / 100)",
    });
    confBtn.type = "button";
    confBtn.addEventListener("click", function () {
      while (panelBody.firstChild) { panelBody.removeChild(panelBody.firstChild); }
      panelBody.appendChild(renderConfidencePanel());
      panelEl.className = "open";
      panelEl.setAttribute("aria-hidden", "false");
    });
    confSec.appendChild(confBtn);
    app.appendChild(confSec);
  }

  var narrSec = section("Narrative");
  var narrP = el("p", { "class": "narrative" });
  linkify(narrP, report.narrative || "No chair narrative is available.");
  narrSec.appendChild(narrP);
  app.appendChild(narrSec);

  var evSec = section("Recommendation evidence");
  evSec.appendChild(idList("Basis", report.recommendation_basis));
  evSec.appendChild(idList("Strongest for", report.strongest_for));
  evSec.appendChild(idList("Strongest against", report.strongest_against));
  app.appendChild(evSec);

  var actSec = section("Required actions");
  if (report.required_actions && report.required_actions.length) {
    var actUl = el("ul");
    report.required_actions.forEach(function (a) {
      var li = el("li");
      li.appendChild(document.createTextNode(a.text + " "));
      (a.source_ids || []).forEach(function (sid, i) {
        if (i) { li.appendChild(document.createTextNode(", ")); }
        li.appendChild(idButton(sid));
      });
      actUl.appendChild(li);
    });
    actSec.appendChild(actUl);
  } else {
    actSec.appendChild(el("p", { text: "None" }));
  }
  app.appendChild(actSec);

  var roleSec = section("Specialist role notes");
  var roleKeys = Object.keys(report.role_notes || {});
  if (roleKeys.length) {
    var rn = el("dl");
    roleKeys.forEach(function (role) {
      rn.appendChild(el("dt", { text: role }));
      rn.appendChild(el("dd", { text: report.role_notes[role] }));
    });
    roleSec.appendChild(rn);
  } else {
    roleSec.appendChild(el("p", { text: "None" }));
  }
  app.appendChild(roleSec);

  var dissSec = section("Dissent");
  if (report.dissent && report.dissent.length) {
    var dul = el("ul");
    report.dissent.forEach(function (d) {
      var li = el("li");
      li.appendChild(document.createTextNode(d.role + " (" + d.stance + ") "));
      li.appendChild(idButton(d.argument_id));
      li.appendChild(el("div", { "class": "meta", text: d.note }));
      dul.appendChild(li);
    });
    dissSec.appendChild(dul);
  } else {
    dissSec.appendChild(el("p", { text: "No dissent" }));
  }
  app.appendChild(dissSec);

  var argSec = section("Arguments");
  [1, 2].forEach(function (round) {
    var roundArgs = (bundle.arguments || []).filter(function (a) { return a.round === round; });
    if (!roundArgs.length) { return; }
    argSec.appendChild(el("h3", { text: "Round " + round }));
    var ul = el("ul");
    roundArgs.forEach(function (a) {
      var li = el("li");
      li.appendChild(idButton(a.argument_id));
      var suffix = a.status === "failed" ? " (failed)" : " — " + a.stance;
      li.appendChild(document.createTextNode(" — " + a.role + suffix));
      ul.appendChild(li);
    });
    argSec.appendChild(ul);
  });
  app.appendChild(argSec);

  var rcSec = section("Round 1 vs Round 2");
  var rc = bundle.scorecard.round_comparison || [];
  if (rc.length) {
    var table = el("table");
    var thead = el("thead");
    var headRow = el("tr");
    ["Role", "R1 score", "R2 score", "Change", "R1 ungrounded", "R2 ungrounded",
      "Kept", "Revised", "Dropped", "R2 status"].forEach(function (h) {
        headRow.appendChild(el("th", { text: h }));
      });
    thead.appendChild(headRow);
    table.appendChild(thead);
    var tbody = el("tbody");
    rc.forEach(function (row) {
      var tr = el("tr");
      [
        row.role,
        row.shared_score.round1 != null ? row.shared_score.round1.toFixed(2) : "—",
        row.shared_score.round2 != null ? row.shared_score.round2.toFixed(2) : "—",
        row.shared_score.change != null ? row.shared_score.change.toFixed(2) : "—",
        row.ungrounded_claims.round1 != null ? row.ungrounded_claims.round1 : "—",
        row.ungrounded_claims.round2 != null ? row.ungrounded_claims.round2 : "—",
        row.revisions.kept, row.revisions.revised, row.revisions.dropped,
        row.round2_status,
      ].forEach(function (v) { tr.appendChild(el("td", { text: String(v) })); });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    rcSec.appendChild(table);
  } else {
    rcSec.appendChild(el("p", { text: "No round comparison data" }));
  }
  app.appendChild(rcSec);

  var rtSec = section("Red team findings");
  var ic = report.injection_check;
  rtSec.appendChild(el("p", { "class": "meta", text: "Injection check verdict: " + ic.verdict + " — " + ic.notes }));
  if (findings.length) {
    var ful = el("ul");
    findings.forEach(function (f) {
      var li = el("li");
      li.appendChild(idButton(f.finding_id));
      li.appendChild(document.createTextNode(" — " + f.severity + " " + f.category + ": " + f.description));
      ful.appendChild(li);
    });
    rtSec.appendChild(ful);
  } else {
    rtSec.appendChild(el("p", { text: "No findings recorded" }));
  }
  app.appendChild(rtSec);

  var jsSec = section("Judges");
  var js = report.judge_summary;
  var jm = "Mean score — Round 1: " + (js.mean_score.round1 != null ? js.mean_score.round1.toFixed(2) : "n/a") +
    ", Round 2: " + (js.mean_score.round2 != null ? js.mean_score.round2.toFixed(2) : "n/a") +
    ". Disagreements (final round): " + js.disagreement_count;
  jsSec.appendChild(el("p", { text: jm }));
  if (js.failed_judge_calls && js.failed_judge_calls.length) {
    var fjul = el("ul");
    js.failed_judge_calls.forEach(function (c) {
      fjul.appendChild(el("li", { text: c.judge + " failed on " + c.argument_id + " (Round " + c.round + ")" }));
    });
    jsSec.appendChild(fjul);
  }
  app.appendChild(jsSec);

  var citSec = section("All citations");
  var citUl = el("ul");
  (report.citations_index || []).forEach(function (c) {
    var li = el("li", { "class": c.verified ? "verified" : "unverified" });
    li.appendChild(idButton(c.passage_id));
    var suffix = ' "' + c.quote + '"' +
      (c.verified ? " [verified]" : " [NOT VERIFIED" + (c.verify_note ? ": " + c.verify_note : "") + "]");
    li.appendChild(document.createTextNode(suffix));
    citUl.appendChild(li);
  });
  if (!report.citations_index || !report.citations_index.length) { citUl.appendChild(el("li", { text: "None" })); }
  citSec.appendChild(citUl);
  app.appendChild(citSec);

  var hdSec = section("Human decision");
  if (report.human_decision) {
    var hd = report.human_decision;
    var hdText = hd.decision + " by " + hd.reviewer + " at " + hd.decided_at +
      (hd.comment ? " — " + hd.comment : "");
    hdSec.appendChild(el("p", { text: hdText }));
  } else {
    hdSec.appendChild(el("p", { text: "Pending human clinical sign-off." }));
  }
  app.appendChild(hdSec);
})();
""".strip()
