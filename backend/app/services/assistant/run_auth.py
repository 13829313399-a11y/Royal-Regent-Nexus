"""Internal session binding; no cookie, token hash or provider key is persisted."""
from dataclasses import dataclass, field
from types import SimpleNamespace
from app.models.auth import AuthSession
from app.services.auth import authenticated_session_user
from .errors import AssistantError


@dataclass
class RunRequest:
    auth_session_id: str
    owner_id: str
    employment_epoch: int
    context_key: str | None
    has_page: bool
    run_id: str
    state: SimpleNamespace = field(init=False)
    termination_reason: str = 'worker_shutdown'

    def __post_init__(self):
        self.state = SimpleNamespace(request_id=self.run_id)

    async def is_disconnected(self):
        return False

    def authenticate(self, db):
        from .service import epoch
        user = authenticated_session_user(db, db.get(AuthSession, self.auth_session_id),
            method='POST', path='/api/assistant/sessions/' + self.run_id + '/messages')
        if user.id != self.owner_id or epoch(user) != self.employment_epoch:
            raise AssistantError('identity_changed', '身份已更新，本次生成已停止。', 403)
        if self.has_page and (user.identity or {}).get('effective_context_key') != self.context_key:
            raise AssistantError('context_changed', '任职或授权已更新，请重新选择页面说明。', 403)
        return user
