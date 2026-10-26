"""Bounded per-process XLSX generation; never wait while holding a DB transaction.

This limits CPU-heavy rendering in one API worker, not across a multi-worker fleet.
No report, authorization or business value is cached.
"""
from contextlib import contextmanager
from collections import deque
from threading import Condition
from time import monotonic
from fastapi import HTTPException


class ExportGate:
    def __init__(self, capacity=16, timeout=20, parallelism=1):
        if not 1 <= parallelism <= capacity:
            raise ValueError('Renderer concurrency must fit queue capacity')
        self.capacity = capacity
        self.parallelism = parallelism
        self.condition = Condition()
        self.waiters = deque()
        self.active = 0
        self.timeout = timeout

    @contextmanager
    def slot(self):
        ticket = object()
        with self.condition:
            if len(self.waiters) + self.active >= self.capacity:
                raise HTTPException(429, '报表导出队列已满，请稍后重试', headers={'Retry-After': '3'})
            self.waiters.append(ticket)
            deadline = monotonic() + self.timeout
            waited = False
            try:
                # A semaphore permits new arrivals to overtake old waiters.
                # FIFO prevents repeated downloads from starving earlier users.
                while self.active >= self.parallelism or self.waiters[0] is not ticket:
                    remaining = deadline - monotonic()
                    if remaining <= 0:
                        raise HTTPException(429, '报表导出等待超时，请稍后重试', headers={'Retry-After': '3'})
                    waited = True
                    self.condition.wait(remaining)
                if waited and monotonic() >= deadline:
                    raise HTTPException(429, '报表导出等待超时，请稍后重试', headers={'Retry-After': '3'})
                self.waiters.popleft()
                self.active += 1
                self.condition.notify_all()
            except BaseException:
                self.waiters.remove(ticket)
                self.condition.notify_all()
                raise
        try:
            yield
        finally:
            with self.condition:
                self.active -= 1
                self.condition.notify_all()


gate = ExportGate(parallelism=1)
