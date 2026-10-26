"""Bounded publisher hints; a title containing 'official' is never proof."""
import re
from urllib.parse import urlsplit

# Small, explicit catalog of documentation publishers. Unknown topics stay
# unclassified; extend only after checking the publisher's actual documentation.
DOCUMENTATION_DOMAINS = ((r"\bfastapi\b", "fastapi.tiangolo.com"), (r"\bpython\b", "docs.python.org"))


def preferred_domains(public_query):
    domains = [domain for pattern, domain in DOCUMENTATION_DOMAINS if re.search(pattern, public_query, re.I)]
    for host in re.findall(r"\bsite:([a-z0-9.-]+)", public_query, re.I):
        if host not in domains:
            domains.append(host.lower().rstrip('.'))
    return domains


def preferred(source, domains):
    try:
        host = (urlsplit(source.get("url", "")).hostname or "").lower().rstrip('.')
        return host in domains  # No substring or misleading-title matching.
    except ValueError:
        return False


def research_query(query, domains):
    policy = "检索要求：优先原始发布方和官方文档；不要把标题含‘官方’的转载当作官方来源。回答本次追问，不重复上一问。"
    if domains:
        policy += "优先检索站点：" + ", ".join(domains) + "。未取得这些站点来源时如实说明。"
    return query + "\n\n" + policy
