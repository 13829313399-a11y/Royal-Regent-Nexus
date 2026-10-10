"""Private member collaboration. Frozen schema; retain populated tables on rollback."""
from alembic import op
import sqlalchemy as sa

revision = "20261009_0151"
down_revision = "20261009_0150"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('collab_direct_conversations',
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('low_user_id', sa.String(length=64), sa.ForeignKey('auth_users.id'), nullable=False),
        sa.Column('low_epoch', sa.Integer(), nullable=False),
        sa.Column('high_user_id', sa.String(length=64), sa.ForeignKey('auth_users.id'), nullable=False),
        sa.Column('high_epoch', sa.Integer(), nullable=False),
        sa.Column('last_message_seq', sa.Integer(), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.String(length=32), nullable=False),
        sa.Column('updated_at', sa.String(length=32), nullable=False),
        sa.CheckConstraint('low_user_id < high_user_id', name='ck_collab_distinct_ordered_pair'),
        sa.UniqueConstraint('low_user_id', 'low_epoch', 'high_user_id', 'high_epoch', name='uq_collab_pair'),
    )
    op.create_index('ix_collab_direct_conversations_updated_at', 'collab_direct_conversations', ['updated_at'])
    op.create_table('collab_user_events',
        sa.Column('user_id', sa.String(length=64), sa.ForeignKey('auth_users.id'), nullable=False, primary_key=True),
        sa.Column('epoch', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('event_seq', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('event_type', sa.String(length=40), nullable=False),
        sa.Column('entity_id', sa.String(length=64), nullable=False),
        sa.Column('entity_version', sa.Integer(), nullable=False),
        sa.Column('conversation_id', sa.String(length=64), nullable=False),
        sa.Column('actor_id', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.String(length=32), nullable=False),
    )
    op.create_index('ix_collab_user_events_created_at', 'collab_user_events', ['created_at'])
    op.create_table('collab_user_streams',
        sa.Column('user_id', sa.String(length=64), sa.ForeignKey('auth_users.id'), nullable=False, primary_key=True),
        sa.Column('epoch', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('last_event_seq', sa.Integer(), nullable=False),
        sa.Column('minimum_valid_cursor', sa.Integer(), nullable=False),
    )
    op.create_table('member_appreciations',
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('sender_id', sa.String(length=64), sa.ForeignKey('auth_users.id'), nullable=False),
        sa.Column('sender_epoch', sa.Integer(), nullable=False),
        sa.Column('receiver_id', sa.String(length=64), sa.ForeignKey('auth_users.id'), nullable=False),
        sa.Column('receiver_epoch', sa.Integer(), nullable=False),
        sa.Column('client_request_id', sa.String(length=96), nullable=False),
        sa.Column('request_hash', sa.String(length=64), nullable=False),
        sa.Column('category', sa.String(length=32), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('created_at', sa.String(length=32), nullable=False),
        sa.Column('receiver_seen_at', sa.String(length=32), nullable=True),
        sa.Column('private_pin_order', sa.Integer(), nullable=False),
        sa.Column('hidden_at', sa.String(length=32), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.UniqueConstraint('sender_id', 'sender_epoch', 'client_request_id', name='uq_member_appreciation_client'),
    )
    op.create_index('ix_appreciation_received', 'member_appreciations', ['receiver_id', 'receiver_epoch', 'created_at'])
    op.create_table('member_contacts',
        sa.Column('user_id', sa.String(length=64), sa.ForeignKey('auth_users.id'), nullable=False, primary_key=True),
        sa.Column('epoch', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('target_id', sa.String(length=64), sa.ForeignKey('auth_users.id'), nullable=False, primary_key=True),
        sa.Column('target_epoch', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('pin_order', sa.Integer(), nullable=False),
    )
    op.create_table('member_preferences',
        sa.Column('user_id', sa.String(length=64), sa.ForeignKey('auth_users.id'), nullable=False, primary_key=True),
        sa.Column('epoch', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('values', sa.JSON(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
    )
    op.create_table('member_social_profiles',
        sa.Column('user_id', sa.String(length=64), sa.ForeignKey('auth_users.id'), nullable=False, primary_key=True),
        sa.Column('epoch', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('bio', sa.Text(), nullable=False),
        sa.Column('help_topics', sa.String(length=80), nullable=False),
        sa.Column('skill_tags', sa.JSON(), nullable=False),
        sa.Column('theme', sa.String(length=16), nullable=False),
        sa.Column('availability', sa.String(length=20), nullable=False),
        sa.Column('status_text', sa.String(length=60), nullable=False),
        sa.Column('status_expires_at', sa.String(length=32), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
    )
    op.create_table('collab_conversation_members',
        sa.Column('conversation_id', sa.String(length=64), sa.ForeignKey('collab_direct_conversations.id'), nullable=False, primary_key=True),
        sa.Column('user_id', sa.String(length=64), sa.ForeignKey('auth_users.id'), nullable=False, primary_key=True),
        sa.Column('epoch', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('last_read_seq', sa.Integer(), nullable=False),
        sa.Column('mute_until', sa.String(length=32), nullable=True),
        sa.Column('pin_order', sa.Integer(), nullable=False),
        sa.Column('archived_at', sa.String(length=32), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
    )
    op.create_index('ix_collab_member_owner', 'collab_conversation_members', ['user_id', 'epoch', 'conversation_id'])
    op.create_table('collab_drafts',
        sa.Column('conversation_id', sa.String(length=64), sa.ForeignKey('collab_direct_conversations.id'), nullable=False, primary_key=True),
        sa.Column('user_id', sa.String(length=64), sa.ForeignKey('auth_users.id'), nullable=False, primary_key=True),
        sa.Column('epoch', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('reply_to_id', sa.String(length=64), nullable=True),
        sa.Column('attachment_ids', sa.JSON(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.String(length=32), nullable=False),
    )
    op.create_table('collab_messages',
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('conversation_id', sa.String(length=64), sa.ForeignKey('collab_direct_conversations.id'), nullable=False),
        sa.Column('message_seq', sa.Integer(), nullable=False),
        sa.Column('sender_user_id', sa.String(length=64), sa.ForeignKey('auth_users.id'), nullable=False),
        sa.Column('sender_epoch', sa.Integer(), nullable=False),
        sa.Column('client_message_id', sa.String(length=96), nullable=False),
        sa.Column('request_hash', sa.String(length=64), nullable=False),
        sa.Column('kind', sa.String(length=24), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('reply_to_id', sa.String(length=64), sa.ForeignKey('collab_messages.id'), nullable=True),
        sa.Column('reference', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.String(length=32), nullable=False),
        sa.Column('retracted_at', sa.String(length=32), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.UniqueConstraint('sender_user_id', 'sender_epoch', 'client_message_id', name='uq_collab_message_client'),
        sa.UniqueConstraint('conversation_id', 'message_seq', name='uq_collab_message_seq'),
    )
    op.create_index('ix_collab_message_unread', 'collab_messages', ['conversation_id', 'sender_user_id', 'message_seq'])
    op.create_table('collab_attachments',
        sa.Column('id', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('owner_id', sa.String(length=64), sa.ForeignKey('auth_users.id'), nullable=False),
        sa.Column('epoch', sa.Integer(), nullable=False),
        sa.Column('client_upload_id', sa.String(length=96), nullable=False),
        sa.Column('request_hash', sa.String(length=64), nullable=False),
        sa.Column('conversation_id', sa.String(length=64), sa.ForeignKey('collab_direct_conversations.id'), nullable=False),
        sa.Column('message_id', sa.String(length=64), sa.ForeignKey('collab_messages.id'), nullable=True),
        sa.Column('storage_key', sa.String(length=128), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('mime', sa.String(length=128), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('state', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.String(length=32), nullable=False),
        sa.UniqueConstraint('owner_id', 'epoch', 'client_upload_id', name='uq_collab_upload'),
    )
    op.create_index('ix_collab_attachments_message_id', 'collab_attachments', ['message_id'])
    op.create_index('ix_collab_pending_assets', 'collab_attachments', ['state', 'created_at'])


def downgrade():
    # Operational rollback disables the feature and retains all private history.
    bind = op.get_bind()
    if bind.execute(sa.text('SELECT 1 FROM collab_direct_conversations LIMIT 1')).first():
        raise RuntimeError("Collaboration contains data; disable the feature instead of dropping private history")
    if bind.execute(sa.text('SELECT 1 FROM collab_user_events LIMIT 1')).first():
        raise RuntimeError("Collaboration contains data; disable the feature instead of dropping private history")
    if bind.execute(sa.text('SELECT 1 FROM collab_user_streams LIMIT 1')).first():
        raise RuntimeError("Collaboration contains data; disable the feature instead of dropping private history")
    if bind.execute(sa.text('SELECT 1 FROM member_appreciations LIMIT 1')).first():
        raise RuntimeError("Collaboration contains data; disable the feature instead of dropping private history")
    if bind.execute(sa.text('SELECT 1 FROM member_contacts LIMIT 1')).first():
        raise RuntimeError("Collaboration contains data; disable the feature instead of dropping private history")
    if bind.execute(sa.text('SELECT 1 FROM member_preferences LIMIT 1')).first():
        raise RuntimeError("Collaboration contains data; disable the feature instead of dropping private history")
    if bind.execute(sa.text('SELECT 1 FROM member_social_profiles LIMIT 1')).first():
        raise RuntimeError("Collaboration contains data; disable the feature instead of dropping private history")
    if bind.execute(sa.text('SELECT 1 FROM collab_conversation_members LIMIT 1')).first():
        raise RuntimeError("Collaboration contains data; disable the feature instead of dropping private history")
    if bind.execute(sa.text('SELECT 1 FROM collab_drafts LIMIT 1')).first():
        raise RuntimeError("Collaboration contains data; disable the feature instead of dropping private history")
    if bind.execute(sa.text('SELECT 1 FROM collab_messages LIMIT 1')).first():
        raise RuntimeError("Collaboration contains data; disable the feature instead of dropping private history")
    if bind.execute(sa.text('SELECT 1 FROM collab_attachments LIMIT 1')).first():
        raise RuntimeError("Collaboration contains data; disable the feature instead of dropping private history")
    op.drop_table('collab_attachments')
    op.drop_table('collab_messages')
    op.drop_table('collab_drafts')
    op.drop_table('collab_conversation_members')
    op.drop_table('member_social_profiles')
    op.drop_table('member_preferences')
    op.drop_table('member_contacts')
    op.drop_table('member_appreciations')
    op.drop_table('collab_user_streams')
    op.drop_table('collab_user_events')
    op.drop_table('collab_direct_conversations')
