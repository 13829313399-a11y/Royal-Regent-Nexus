"""Managed DB queue and private ordered replay. Reconnection never executes a run."""
import asyncio
from contextlib import suppress
from copy import deepcopy
import json
import hashlib
import logging
import time
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select
from app import db as database
from app.core.config import settings
from app.models.assistant import (AssistantRun as Run, AssistantSession as Conversation,
    AssistantMessage as Message, AssistantExecution as Execution, AssistantRunEvent as Event,
    AssistantProviderStep as Step)
from app.models.auth import AuthSession
from app.services.auth import authenticated_session_user
from . import service, visibility, help_registry
from .errors import AssistantError
from .run_auth import RunRequest

logger = logging.getLogger('assistant.worker')


def validate_binding(db, user, ident):
    bound = authenticated_session_user(db, db.get(AuthSession, ident) if ident else None,
        method='POST', path='/api/assistant/sessions/messages')
    if bound.id != user.id or service.epoch(bound) != service.epoch(user):
        raise AssistantError('identity_changed', '身份已更新，请重新登录。', 403)


def enqueue(db, run, user, auth_session_id, dependencies):
    limits = dict(run_seconds=settings.assistant_run_timeout_seconds,
        step_seconds=settings.assistant_step_timeout_seconds, tool_rounds=settings.assistant_max_tool_rounds,
        context_characters=settings.assistant_context_character_budget, output_tokens=settings.assistant_max_output_tokens,
        connection_stamp=connection_stamp())
    # A queued request may survive process restart, within its original deadline.
    run.lease_expires_at = run.started_at + limits['run_seconds']
    db.add(Execution(run_id=run.id, auth_session_id=auth_session_id,
        context_key=(user.identity or {}).get('effective_context_key'), status='queued',
        worker_id=None, fence=0, last_seq=0, queued_at=run.started_at, claimed_at=None,
        limits=limits, source_refs=deepcopy(dependencies)))


def connection_stamp():
    from .capabilities import profile
    current = profile()
    value = dict(provider=settings.assistant_provider, model=settings.assistant_model,
        endpoint=settings.assistant_qwen_base_url, search_endpoint=settings.assistant_search_endpoint,
        search_region=settings.assistant_search_region, profile=current.model_dump(mode='json') if current else None)
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _append(db, execution, kind, payload):
    execution.last_seq += 1
    data = dict(payload, run_id=execution.run_id, seq=execution.last_seq)
    db.add(Event(run_id=execution.run_id, seq=execution.last_seq, kind=kind,
        payload=deepcopy(data), created_at=time.time()))


def checkpoint(db, run, message, *, event=None, terminal=False, terminal_data=None):
    """Called under the same DB lock as message/terminal writes, never afterward."""
    execution = db.get(Execution, run.id)
    if execution is None:
        raise AssistantError('durable_schema_pending', '运行队列记录不完整，已停止。', 503)
    refs = {s['source_id']: s for s in execution.source_refs}
    refs.update({s['source_id']: s for s in visibility.sources(message.content_parts)})
    execution.source_refs = deepcopy(list(refs.values()))
    if terminal:
        if execution.status == 'terminal':
            return
        execution.status = 'terminal'
        # Crash settlement may not have passed through the live RunContent.
        parts = deepcopy(message.content_parts)
        for part in parts:
            if part.get('type') != 'evidence':
                continue
            for activity in part.get('activities', []):
                if activity.get('status') == 'running':
                    from .evidence import now_iso
                    activity.update(status='cancelled' if run.state == 'cancelled' else 'failed', finished_at=now_iso())
            for citation in part.get('citations', []):
                if citation.get('resolution') == 'pending':
                    citation['resolution'] = 'unresolved'
            if part.get('search', {}).get('execution') == 'pending':
                part['search'].update(execution='failed', reason_code=run.error_code or run.state)
            part['revision'] += 1
        message.content_parts = parts
        for step in db.scalars(select(Step).where(Step.run_id == run.id, Step.status == 'started')):
            step.status, step.finished_at = 'unknown', time.time()
        data = dict(terminal_data or {}, code=run.error_code, usage=run.usage)
        if run.state != 'completed':
            data['outcome'] = 'partial'
            data.setdefault('message', '生成已停止，已保存收到的部分内容。' if run.state == 'cancelled'
                else '生成已中断，已保存收到的部分内容；需要继续时请显式重试。')
            data.setdefault('retryable', True)
        _append(db, execution, 'run.' + run.state, data)
    elif event:
        _append(db, execution, event[0], event[1])


def record(rid, lease, kind, data, parts, citations, phase):
    if kind.startswith('run.') and kind != 'run.started':
        return  # Terminal events are committed atomically by service.control.
    state = service.control(rid, lease, parts=parts, citations=citations, state=phase,
        durable_event=(kind, data))
    if state not in service.ACTIVE:
        raise AssistantError('cancelled', '生成已停止，内容已保留。', 409)


def _owned_execution(db, rid, lease):
    run, execution = db.get(Run, rid), db.get(Execution, rid)
    if (not run or not execution or execution.status != 'running' or run.lease_owner != lease
            or run.state not in service.ACTIVE or run.lease_expires_at < time.time()
            or run.cancel_requested or not settings.assistant_enabled or not settings.assistant_durable_runs_enabled):
        raise AssistantError('lease_lost', '生成已中断，请查看保存的回答。', 409)
    return run, execution


def begin_step(rid, lease, step_id, provider):
    with service.transaction() as db:
        run, execution = _owned_execution(db, rid, lease)
        limits = execution.limits
        if (connection_stamp() != limits['connection_stamp']
                or settings.assistant_context_character_budget > limits['context_characters']
                or (limits['output_tokens'] is not None and (settings.assistant_max_output_tokens is None
                    or settings.assistant_max_output_tokens > limits['output_tokens']))):
            raise AssistantError('execution_limits_changed', '生成预算配置已改变，请核对后显式重试。', 409)
        if db.get(Step, (rid, step_id)) is not None:
            raise AssistantError('step_already_attempted', '该步骤已发出，不能自动重复生成。', 409)
        count = db.scalars(select(Step.step_id).where(Step.run_id == rid)).all()
        max_steps = limits['tool_rounds'] + 1 + int(run.request_input.get('web_search') != 'off')
        if len(count) >= max_steps:
            raise AssistantError('tool_limit', '本次生成步骤已达到上限。', 429)
        if time.time() >= run.started_at + limits['run_seconds']:
            raise AssistantError('run_timeout', '本次生成达到配置时限，已保留回答。', 504)
        budget = limits['context_characters'] * 4 + limits['output_tokens'] if limits['output_tokens'] else None
        db.add(Step(run_id=rid, step_id=step_id, fence=execution.fence, provider=provider,
            status='started', budget_tokens=budget, request_id=None, usage=None,
            started_at=time.time(), finished_at=None))
        # A previous step's known total cannot stand in for the newly issued,
        # still unknown step if this process crashes before its next checkpoint.
        run.usage = None
        run.context_window = {**run.context_window, 'provider_attempt_state': 'started'}


def update_step(rid, lease, step_id, *, request_id=None, usage=service.UNSET, run_usage=service.UNSET):
    with service.transaction() as db:
        run, execution = _owned_execution(db, rid, lease)
        step = db.get(Step, (rid, step_id))
        if not step or step.fence != execution.fence or step.status != 'started':
            raise AssistantError('step_fence_lost', '生成步骤的执行权已失效。', 409)
        if request_id:
            step.request_id = request_id
            run.provider_request_id = request_id
        if usage is not service.UNSET:
            step.usage = usage
        if run_usage is not service.UNSET:
            run.usage = run_usage


def finish_step(rid, lease, step_id, request_id, usage):
    with service.transaction() as db:
        _, execution = _owned_execution(db, rid, lease)
        step = db.get(Step, (rid, step_id))
        if not step or step.fence != execution.fence or step.status != 'started':
            raise AssistantError('step_fence_lost', '生成步骤的执行权已失效。', 409)
        step.status, step.finished_at, step.request_id, step.usage = 'completed', time.time(), request_id, usage


def claim(worker_id):
    with service.transaction() as db:
        service.settle_expired(db)
        if not settings.assistant_enabled or not settings.assistant_durable_runs_enabled:
            return None
        execution = db.scalar(select(Execution).join(Run).where(Execution.status == 'queued',
            Run.state.in_(service.ACTIVE)).order_by(Execution.queued_at, Execution.run_id).limit(1))
        if execution is None:
            return None
        run = db.get(Run, execution.run_id)
        execution.worker_id, execution.status, execution.claimed_at = worker_id, 'running', time.time()
        execution.fence += 1
        run.lease_owner, run.lease_expires_at = uuid4().hex, time.time() + service.LEASE_SECONDS
        session = db.get(Conversation, run.session_id)
        message = db.scalar(select(Message).where(Message.run_id == run.id, Message.role == 'assistant'))
        request = RunRequest(execution.auth_session_id, session.owner_user_id, session.employment_epoch,
            execution.context_key, bool(run.request_input.get('page_context')), run.id)
        return dict(request=request, frozen=deepcopy(run.request_input), limits=deepcopy(execution.limits),
            admitted=dict(run_id=run.id, lease=run.lease_owner, session_id=run.session_id,
                message_id=message.id, citations=deepcopy(message.help_citations),
                limits=deepcopy(execution.limits), deadline=run.started_at + execution.limits['run_seconds']))


@help_registry.scoped_read
def replay(user, rid, after_seq=0, limit=200):
    with service.transaction() as db:
        service.settle_expired(db)
        run = db.get(Run, rid)
        if run is None:
            raise AssistantError('not_found', '没有找到这个请求。', 404)
        service.owned(db, user, run.session_id)
        execution = db.get(Execution, rid)
        if execution is None:
            raise AssistantError('legacy_run', '旧运行请读取保存的回答。', 409)
        messages = db.scalars(select(Message).where(Message.run_id == rid)).all()
        if after_seq > execution.last_seq:
            raise AssistantError('event_cursor_ahead', '订阅位置超出保存进度，请重新读取运行快照。', 409)
        rows = db.scalars(select(Event).where(Event.run_id == rid, Event.seq > after_seq)
            .order_by(Event.seq).limit(limit)).all()
        refs = deepcopy(execution.source_refs)
        result = dict(events=[dict(event=r.kind, data=deepcopy(r.payload)) for r in rows],
            last_seq=execution.last_seq, state=run.state)
    # Native source checks may read files or several domains. Release the write
    # lock first, just as history/snapshot do, so cancellation and checkpoints
    # remain available while a subscriber reauthorizes private material.
    if not visibility.allowed(user, refs) or any(service.message_out(m, user).get('unavailable') for m in messages):
        raise AssistantError('sources_unavailable', '相关资料已删除或授权已改变，当前不可查看。', 410)
    with database.SessionLocal() as db:
        service.owned(db, user, run.session_id)
        latest = db.get(Execution, rid)
        if latest is None:
            raise AssistantError('not_found', '没有找到这个请求。', 404)
        if latest.source_refs != refs:
            # New dependencies arrived during a slow read. Release no old
            # bytes until the next batch has checked the enlarged union.
            return dict(events=[], last_seq=latest.last_seq, state='connecting')
    return result


async def subscription(request, rid, after_seq, subscriber_id=None):
    from . import runtime, operations
    # A finite subscription avoids retaining abandoned proxy connections.
    # The client's next GET resumes this same run and cursor.
    until, heartbeat = time.monotonic() + 25, time.monotonic()
    try:
        while time.monotonic() < until:
            if await request.is_disconnected():return
            try:
                user = await asyncio.to_thread(runtime.authenticate, request)
                batch = await asyncio.to_thread(replay, user, rid, after_seq)
            except HTTPException as exc:
                detail = exc.detail if isinstance(exc.detail, dict) else {}
                data = dict(run_id=rid, code=detail.get('code', 'identity_unavailable'),
                    message='登录或相关资料权限已改变，当前内容已停止展示。')
                yield 'event: run.unavailable\ndata: ' + json.dumps(data, ensure_ascii=False) + '\n\n'
                return
            if subscriber_id and batch['events']:
                with suppress(Exception):
                    await asyncio.to_thread(operations.subscription_sent,rid,subscriber_id,batch['events'][-1]['data']['seq'])
            for event in batch['events']:
                after_seq = event['data']['seq']
                yield 'event: ' + event['event'] + '\ndata: ' + json.dumps(event['data'], ensure_ascii=False) + '\n\n'
            if batch['state'] not in service.ACTIVE and after_seq >= batch['last_seq']:return
            if time.monotonic() - heartbeat >= 10:
                heartbeat = time.monotonic()
                yield ': heartbeat\n\n'
            await asyncio.sleep(.3)
    finally:
        if subscriber_id:
            with suppress(Exception):
                await asyncio.shield(asyncio.to_thread(operations.subscription_closed,rid,subscriber_id))


class DurableWorker:
    def __init__(self):
        self.instance_id = uuid4().hex
        self.supervisor = None
        self.tasks = {}

    @property
    def running(self):
        return self.supervisor is not None and not self.supervisor.done()

    async def start(self):
        from .capabilities import durable_schema_ready
        if self.running or not settings.assistant_durable_runs_enabled or not await asyncio.to_thread(durable_schema_ready):
            return
        self.instance_id = uuid4().hex
        self.supervisor = asyncio.create_task(self._loop(), name='assistant-durable-worker')

    async def stop(self):
        if self.supervisor:
            self.supervisor.cancel()
            with suppress(asyncio.CancelledError):
                await self.supervisor
            self.supervisor = None
        tasks = list(self.tasks.values())
        for task, _ in tasks:
            task.cancel()
        await asyncio.gather(*(t for t, _ in tasks), return_exceptions=True)
        self.tasks.clear()

    async def _execute(self, work):
        from . import runtime
        from app.schemas.assistant import SendMessage
        admitted, request = work['admitted'], work['request']
        try:
            user = await asyncio.to_thread(runtime.authenticate, request)
            # Reconstruct public help only after fresh native authentication.
            await asyncio.to_thread(help_registry.require_references, user, admitted['citations'])
            await asyncio.to_thread(replay, user, admitted['run_id'])
            admitted['citations'] = await asyncio.to_thread(restore_citations, user, admitted['citations'])
            payload = SendMessage.model_validate(work['frozen'])
            async for _ in runtime.events(request, user, payload, admitted):
                pass
        except asyncio.CancelledError:
            with suppress(Exception):
                await asyncio.shield(asyncio.to_thread(service.control, admitted['run_id'], admitted['lease'],
                    terminal='interrupted', error='worker_shutdown'))
            raise
        except Exception as exc:
            code = exc.detail.get('code', 'identity_unavailable') if isinstance(exc, HTTPException) and isinstance(exc.detail, dict) else 'identity_unavailable' if isinstance(exc, HTTPException) else 'worker_failed'
            with suppress(Exception):
                await asyncio.to_thread(service.control, admitted['run_id'], admitted['lease'], terminal='interrupted', error=code)
            logger.warning('run_id=%s code=%s', admitted['run_id'], code)
        finally:
            with suppress(Exception):
                await asyncio.to_thread(service.cleanup, admitted['session_id'])

    def _monitor(self, rid, lease, renew):
        with service.transaction() as db:
            service.settle_expired(db)
            run = db.get(Run, rid)
            if not run or run.state not in service.ACTIVE:
                return False
            execution = db.get(Execution, rid)
            if execution and time.time() >= run.started_at + execution.limits['run_seconds']:
                service._control(db, run, lease, terminal='failed', error='run_timeout')
                return False
            if run.cancel_requested or not settings.assistant_enabled or not settings.assistant_durable_runs_enabled:
                service._control(db, run, lease, terminal='cancelled' if run.cancel_requested else 'interrupted',
                    error='cancelled' if run.cancel_requested else 'disabled')
                return False
            if renew:
                service._control(db, run, lease)
            return True

    async def _loop(self):
        last_renew = 0
        while True:
            try:
                now = time.monotonic()
                for rid, (task, lease) in list(self.tasks.items()):
                    if task.done():
                        with suppress(BaseException):
                            task.result()
                        del self.tasks[rid]
                    elif not await asyncio.to_thread(self._monitor, rid, lease, now - last_renew >= 5):
                        task.cancel()
                if now - last_renew >= 5:
                    last_renew = now
                work = await asyncio.to_thread(claim, self.instance_id)
                if work:
                    admitted = work['admitted']
                    self.tasks[admitted['run_id']] = (asyncio.create_task(self._execute(work)), admitted['lease'])
                    continue
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # SQL exceptions can contain private JSON bind parameters.
                logger.error('assistant_worker_tick_failed type=%s', type(exc).__name__)
            await asyncio.sleep(.3)


worker = DurableWorker()


@help_registry.scoped_read
def restore_citations(user, refs):
    result = []
    for ref in refs:
        article = help_registry.get(user, ref['id'])
        if not help_registry.matches(article, ref):
            raise AssistantError('help_changed', '原说明版本已改变，请重新读取当前说明。', 409)
        result.append(help_registry.public(article))
    return result
