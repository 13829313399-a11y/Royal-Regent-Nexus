"""Private collaboration data is owned by an employment identity, never a role."""
from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class MemberProfile(Base):
    __tablename__ = "member_social_profiles"
    user_id: Mapped[str] = mapped_column(ForeignKey("auth_users.id"), primary_key=True)
    epoch: Mapped[int] = mapped_column(Integer, primary_key=True)
    bio: Mapped[str] = mapped_column(Text, default="")
    help_topics: Mapped[str] = mapped_column(String(80), default="")
    skill_tags: Mapped[list] = mapped_column(JSON, default=list)
    theme: Mapped[str] = mapped_column(String(16), default="celadon")
    availability: Mapped[str] = mapped_column(String(20), default="available")
    status_text: Mapped[str] = mapped_column(String(60), default="")
    status_expires_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)


class MemberPreferences(Base):
    __tablename__ = "member_preferences"
    user_id: Mapped[str] = mapped_column(ForeignKey("auth_users.id"), primary_key=True)
    epoch: Mapped[int] = mapped_column(Integer, primary_key=True)
    values: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)


class MemberContact(Base):
    __tablename__ = "member_contacts"
    user_id: Mapped[str] = mapped_column(ForeignKey("auth_users.id"), primary_key=True)
    epoch: Mapped[int] = mapped_column(Integer, primary_key=True)
    target_id: Mapped[str] = mapped_column(ForeignKey("auth_users.id"), primary_key=True)
    target_epoch: Mapped[int] = mapped_column(Integer, primary_key=True)
    pin_order: Mapped[int] = mapped_column(Integer, default=0)


class DirectConversation(Base):
    __tablename__ = "collab_direct_conversations"
    __table_args__ = (
        UniqueConstraint("low_user_id", "low_epoch", "high_user_id", "high_epoch", name="uq_collab_pair"),
        CheckConstraint("low_user_id < high_user_id", name="ck_collab_distinct_ordered_pair"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    low_user_id: Mapped[str] = mapped_column(ForeignKey("auth_users.id"))
    low_epoch: Mapped[int] = mapped_column(Integer)
    high_user_id: Mapped[str] = mapped_column(ForeignKey("auth_users.id"))
    high_epoch: Mapped[int] = mapped_column(Integer)
    last_message_seq: Mapped[int] = mapped_column(Integer, default=0)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(String(32))
    updated_at: Mapped[str] = mapped_column(String(32), index=True)


class ConversationMember(Base):
    __tablename__ = "collab_conversation_members"
    __table_args__ = (Index("ix_collab_member_owner", "user_id", "epoch", "conversation_id"),)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("collab_direct_conversations.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("auth_users.id"), primary_key=True)
    epoch: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_read_seq: Mapped[int] = mapped_column(Integer, default=0)
    mute_until: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pin_order: Mapped[int] = mapped_column(Integer, default=0)
    archived_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)


class Message(Base):
    __tablename__ = "collab_messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "message_seq", name="uq_collab_message_seq"),
        UniqueConstraint("sender_user_id", "sender_epoch", "client_message_id", name="uq_collab_message_client"),
        Index("ix_collab_message_unread", "conversation_id", "sender_user_id", "message_seq"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("collab_direct_conversations.id"))
    message_seq: Mapped[int] = mapped_column(Integer)
    sender_user_id: Mapped[str] = mapped_column(ForeignKey("auth_users.id"))
    sender_epoch: Mapped[int] = mapped_column(Integer)
    client_message_id: Mapped[str] = mapped_column(String(96))
    request_hash: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(24))
    body: Mapped[str] = mapped_column(Text, default="")
    reply_to_id: Mapped[str | None] = mapped_column(ForeignKey("collab_messages.id"), nullable=True)
    reference: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[str] = mapped_column(String(32))
    retracted_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)


class UserStream(Base):
    __tablename__ = "collab_user_streams"
    user_id: Mapped[str] = mapped_column(ForeignKey("auth_users.id"), primary_key=True)
    epoch: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_event_seq: Mapped[int] = mapped_column(Integer, default=0)
    minimum_valid_cursor: Mapped[int] = mapped_column(Integer, default=0)


class UserEvent(Base):
    __tablename__ = "collab_user_events"
    user_id: Mapped[str] = mapped_column(ForeignKey("auth_users.id"), primary_key=True)
    epoch: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(64), default="")
    entity_version: Mapped[int] = mapped_column(Integer, default=1)
    conversation_id: Mapped[str] = mapped_column(String(64), default="")
    actor_id: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[str] = mapped_column(String(32), index=True)


class Attachment(Base):
    __tablename__ = "collab_attachments"
    __table_args__ = (
        UniqueConstraint("owner_id", "epoch", "client_upload_id", name="uq_collab_upload"),
        Index("ix_collab_pending_assets", "state", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("auth_users.id"))
    epoch: Mapped[int] = mapped_column(Integer)
    client_upload_id: Mapped[str] = mapped_column(String(96))
    request_hash: Mapped[str] = mapped_column(String(64))
    conversation_id: Mapped[str] = mapped_column(ForeignKey("collab_direct_conversations.id"))
    message_id: Mapped[str | None] = mapped_column(ForeignKey("collab_messages.id"), nullable=True, index=True)
    storage_key: Mapped[str] = mapped_column(String(128))
    filename: Mapped[str] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(128))
    size: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[str] = mapped_column(String(32))


class Draft(Base):
    __tablename__ = "collab_drafts"
    conversation_id: Mapped[str] = mapped_column(ForeignKey("collab_direct_conversations.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("auth_users.id"), primary_key=True)
    epoch: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text, default="")
    reply_to_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attachment_ids: Mapped[list] = mapped_column(JSON, default=list)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[str] = mapped_column(String(32))


class Appreciation(Base):
    __tablename__ = "member_appreciations"
    __table_args__ = (
        UniqueConstraint("sender_id", "sender_epoch", "client_request_id", name="uq_member_appreciation_client"),
        Index("ix_appreciation_received", "receiver_id", "receiver_epoch", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sender_id: Mapped[str] = mapped_column(ForeignKey("auth_users.id"))
    sender_epoch: Mapped[int] = mapped_column(Integer)
    receiver_id: Mapped[str] = mapped_column(ForeignKey("auth_users.id"))
    receiver_epoch: Mapped[int] = mapped_column(Integer)
    client_request_id: Mapped[str] = mapped_column(String(96))
    request_hash: Mapped[str] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(32))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(32))
    receiver_seen_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    private_pin_order: Mapped[int] = mapped_column(Integer, default=0)
    hidden_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
