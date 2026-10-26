"""Reusable offline V3 harness; real app/database/auth, no paid transport."""
from contextlib import asynccontextmanager
from copy import deepcopy


class ReplayTransport:
    def __init__(self, frames=()):
        self.frames = list(frames)
        self.calls = []

    @asynccontextmanager
    async def open(self, body):
        self.calls.append(deepcopy(body))
        if not self.frames:
            raise AssertionError("No provider replay configured; offline tests must not call a live supplier")
        raw = self.frames.pop(0)
        async def chunks():
            # Deliberately split unicode/SSE boundaries to exercise the production parser.
            encoded = raw.encode("utf-8")
            for start in range(0, len(encoded), 7):
                yield encoded[start:start + 7]
        yield chunks()

    def assert_private_absent(self, literals):
        import json
        data = json.dumps(self.calls, ensure_ascii=False)
        assert all(literal not in data for literal in literals)
