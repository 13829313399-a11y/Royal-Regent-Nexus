"""One run owns all text, evidence and actions; every save is a complete snapshot."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import re
from urllib.parse import urlsplit


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def stable_id(*values):
    return hashlib.sha256("\0".join(str(v) for v in values).encode()).hexdigest()[:24]


def safe_url(value):
    if not isinstance(value, str) or any(c.isspace() or ord(c) < 32 for c in value):
        return None
    try:
        url = urlsplit(value)
        if url.scheme not in ("https", "http") or not url.hostname or url.username or url.password:
            return None
        url.port
        return value
    except ValueError:
        return None


def markers(text):
    # Match Markdown's variable-length fences and inline code delimiters, before
    # looking for complete markers. Rendering uses markdown-it's inline tokens.
    text = re.sub(r"(?ms)^ {0,3}(`{3,}|~{3,})[^\n]*\n.*?(?:^ {0,3}\1[^\n]*(?:\n|$)|\Z)", "", text)
    text = re.sub(r"(`+)(?!`).*?(?<!`)\1(?!`)", "", text, flags=re.S)
    return list(dict.fromkeys(re.findall(r"\[ref_([0-9]+)\]", text)))


class RunContent:
    def __init__(self, run_id, mode="off"):
        self.run_id = run_id
        self.parts = []
        self.actions = []
        self.part_steps = {}
        self.steps = {}
        self.evidence = dict(type="evidence", schema_version=2, run_id=run_id, revision=0,
            search=dict(requested_mode=mode, execution="not_requested" if mode == "off" else "skipped",
                        evidence_level="none", search_count=0, reason_code=None), sources=[], citations=[], activities=[])

    def changed(self):
        self.evidence["revision"] += 1

    def begin(self, step_id, kind, label):
        self.evidence["activities"].append(dict(step_id=step_id, kind=kind, status="running", label=label,
                                               started_at=now_iso(), finished_at=None))
        if kind == "search":
            self.evidence["search"].update(execution="pending", search_count=None, attempted=True)
        self.changed()

    def finish(self, step_id, status="completed"):
        for activity in self.evidence["activities"]:
            if activity["step_id"] == step_id and activity["status"] == "running":
                activity.update(status=status, finished_at=now_iso())
                self.changed()

    def append(self, kind, text, step_id):
        part_id = f"{step_id}:{kind}"
        self.part_steps[part_id] = step_id
        existing = next((p for p in self.parts if p.get("part_id") == part_id), None)
        if existing:
            existing["text"] += text
        else:
            self.parts.append(dict(type=kind, text=text, part_id=part_id))
        self.bind()
        return part_id

    def add_source(self, source):
        sources = self.evidence["sources"]
        old = next((s for s in sources if s["source_id"] == source["source_id"]), None)
        if old == source:
            return
        if old:
            sources[sources.index(old)] = deepcopy(source)
        else:
            sources.append(deepcopy(source))
        web = [s for s in sources if s["kind"] == "web" and not s.get("origin")]
        self.evidence["search"]["evidence_level"] = "pages_fetched" if any(s["evidence_level"] == "page_content" for s in web) else "results_returned" if web else "none"
        self.evidence["search"].update(sources_returned=len(web), pages_read=sum(s["evidence_level"] == "page_content" for s in web))
        self.changed()
        self.bind()

    def web(self, step_id, rows, provider_id=None):
        returned = False
        for row in rows:
            url = safe_url(row.get("url"))
            ref = str(row.get("index", ""))
            if not url or not ref.isdigit():
                continue
            returned = True
            ident = stable_id(self.run_id, step_id, ref)
            old = next((s for s in self.evidence["sources"] if s["source_id"] == ident), None)
            self.add_source(dict(kind="web", source_id=ident, run_id=self.run_id, step_id=step_id,
                provider="dashscope_multimodal", provider_ref=ref, provider_request_id=provider_id,
                title=str(row.get("title") or url)[:500], url=url, site_name=str(row.get("site_name") or urlsplit(url).hostname)[:160],
                retrieved_at=old["retrieved_at"] if old else now_iso(), published_at=None,
                excerpt=str(row.get("snippet") or row.get("summary") or "")[:4000], evidence_level="search_result", read_status="not_attempted"))
        if returned:
            self.evidence["search"].update(execution="confirmed", reason_code=None)
            self.changed()

    def bind(self, terminal=False):
        bindings = []
        for part in self.parts:
            if part["type"] != "text":
                continue
            part_id = part.get("part_id", "")
            step_id = self.part_steps.get(part_id)
            for ref in markers(part["text"]):
                sources = [s["source_id"] for s in self.evidence["sources"]
                           if str(s.get("citation_aliases", {}).get(step_id, s.get("provider_ref", "") if s.get("step_id") == step_id else "")) == ref]
                bindings.append(dict(binding_id=stable_id(self.run_id, part_id, ref), part_id=part_id,
                    marker=f"[ref_{ref}]", source_ids=sources, resolution="resolved" if sources else "unresolved" if terminal else "pending"))
        if bindings != self.evidence["citations"]:
            self.evidence["citations"] = bindings
            self.changed()

    def citation_context(self, step_id):
        eligible = [s for s in self.evidence['sources'] if s.get('citation_eligible',True)]
        for index, source in enumerate(eligible, 1):
            source.setdefault("citation_aliases", {})[step_id] = str(index)
        self.changed()
        self.bind()
        # The full authorized resource registry stays in persisted evidence and
        # is rechecked on every read/action. It is not needed a second time in
        # citation metadata: tool rows already carry their exact record refs.
        return [{**{k: v for k, v in s.items() if k not in (
            {"resources", "authorization_fingerprint", "responsibility_fingerprint", "financial_access", "citation_aliases"} if s["kind"] == "business" else {"citation_aliases"}
        )}, "citation_ref": s["citation_aliases"][step_id]} for s in eligible]

    def account(self, step_id, *, usage=None, search_count=None, request_id=None):
        step = self.steps.setdefault(step_id, dict(step_id=step_id, provider_request_id=None, tokens=None, search_count=None))
        if usage is not None:
            step["tokens"] = {k: usage.get(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens")}
        if request_id:
            step["provider_request_id"] = request_id
        if search_count is not None:
            step["search_count"] = search_count
            search_steps = [self.steps.get(a["step_id"], {}) for a in self.evidence["activities"] if a["kind"] == "search"]
            counts = [s.get("search_count") for s in search_steps]
            self.evidence["search"]["search_count"] = sum(counts) if counts and all(c is not None for c in counts) else None if counts else 0
            # Provider plugin count is diagnostic metadata, not returned evidence.
            self.changed()

    def usage_summary(self):
        steps = list(self.steps.values())
        def total(key):
            values = [(s["tokens"] or {}).get(key) for s in steps]
            return sum(values) if values and all(v is not None for v in values) else None
        tokens = {k: total(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens")}
        counts = [s["search_count"] for s in steps]
        count = sum(counts) if counts and all(c is not None for c in counts) else None
        return dict(schema_version=2, complete=all(v is not None for v in tokens.values()) and count is not None,
                    tokens=tokens, search_count=count, steps=deepcopy(steps))

    def terminal(self, state, code=None):
        for activity in self.evidence["activities"]:
            self.finish(activity["step_id"], "completed" if state == "completed" else "cancelled" if state == "cancelled" else "failed")
        search = self.evidence["search"]
        if search["execution"] == "pending":
            search.update(execution="unconfirmed" if state == "completed" else "failed", reason_code=code or "search_evidence_missing")
            self.changed()
        self.bind(terminal=True)

    def snapshot(self, v2=True):
        parts = deepcopy(self.parts)
        # Provenance is a persistence boundary, independent of the client wire version.
        if v2 or self.evidence["sources"]:
            parts.append(deepcopy(self.evidence))
            if self.actions:
                parts.append(dict(type="actions", schema_version=2, revision=self.evidence["revision"], items=deepcopy(self.actions)))
        return parts
