"""Expand managed source scopes so concrete denials also constrain wildcards."""
from app.services.identity_catalog import FACTORIES, DEPARTMENTS


def complete_scopes(scopes):
    """Retain wildcard authority requirements and evaluate concrete deny tuples."""
    result = set(scopes)
    for factory, department in tuple(result):
        result.update((f, d) for f in (FACTORIES if factory == "*" else [factory])
                      for d in (DEPARTMENTS if department == "*" else [department]))
        # The functional organization is an identity scope, not a production factory.
        if factory == "*" and department in {"*", "management"}:
            result.add(("group-management", "management"))
    return result
