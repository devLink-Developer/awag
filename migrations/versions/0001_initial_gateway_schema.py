"""Initial gateway schema

Revision ID: 0001
Revises:
"""
from alembic import op
import sqlalchemy as sa


revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('instances',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('adb_serial', sa.String(length=128), nullable=False),
    sa.Column('appium_url', sa.String(length=512), nullable=False),
    sa.Column('system_port', sa.Integer(), nullable=False),
    sa.Column('status', sa.Enum('OFFLINE', 'BOOTING', 'ONLINE', 'WHATSAPP_READY', 'BUSY', 'ERROR', name='instancestatus', native_enum=False, create_constraint=False), nullable=False),
    sa.Column('phone_number', sa.String(length=32), nullable=True),
    sa.Column('health', sa.JSON(), nullable=True),
    sa.Column('health_checked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('appium_session_id', sa.String(length=128), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("status IN ('OFFLINE', 'BOOTING', 'ONLINE', 'WHATSAPP_READY', 'BUSY', 'ERROR')", name='instancestatus'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('adb_serial'),
    sa.UniqueConstraint('system_port')
    )
    op.create_table('media',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('type', sa.Enum('text', 'image', 'document', 'audio', 'video', name='messagetype', native_enum=False, create_constraint=False), nullable=False),
    sa.Column('original_name', sa.String(length=255), nullable=False),
    sa.Column('storage_name', sa.String(length=128), nullable=False),
    sa.Column('mime_type', sa.String(length=128), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("type IN ('text', 'image', 'document', 'audio', 'video')", name='messagetype'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('storage_name')
    )
    op.create_table('messages',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('instance_id', sa.Uuid(), nullable=False),
    sa.Column('recipient', sa.String(length=32), nullable=False),
    sa.Column('text', sa.Text(), nullable=True),
    sa.Column('type', sa.Enum('text', 'image', 'document', 'audio', 'video', name='messagetype', native_enum=False, create_constraint=False), nullable=False),
    sa.Column('media_id', sa.Uuid(), nullable=True),
    sa.Column('status', sa.Enum('QUEUED', 'PROCESSING', 'SENT', 'FAILED', name='messagestatus', native_enum=False, create_constraint=False), nullable=False),
    sa.Column('error', sa.String(length=128), nullable=True),
    sa.Column('idempotency_key', sa.String(length=200), nullable=True),
    sa.Column('payload_hash', sa.String(length=64), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('run_token', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('send_started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('evidence', sa.JSON(), nullable=True),
    sa.CheckConstraint("status IN ('QUEUED', 'PROCESSING', 'SENT', 'FAILED')", name='messagestatus'),
    sa.CheckConstraint("type IN ('text', 'image', 'document', 'audio', 'video')", name='messagetype'),
    sa.ForeignKeyConstraint(['instance_id'], ['instances.id'], ),
    sa.ForeignKeyConstraint(['media_id'], ['media.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('instance_id', 'idempotency_key', name='uq_message_idempotency')
    )
    op.create_index(op.f('ix_messages_instance_id'), 'messages', ['instance_id'], unique=False)
    op.create_index(op.f('ix_messages_status'), 'messages', ['status'], unique=False)
    op.create_table('outbox',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('message_id', sa.Uuid(), nullable=False),
    sa.Column('available_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['message_id'], ['messages.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_outbox_available_at'), 'outbox', ['available_at'], unique=False)
    op.create_index(op.f('ix_outbox_message_id'), 'outbox', ['message_id'], unique=False)
    op.create_index(op.f('ix_outbox_published_at'), 'outbox', ['published_at'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_outbox_published_at'), table_name='outbox')
    op.drop_index(op.f('ix_outbox_message_id'), table_name='outbox')
    op.drop_index(op.f('ix_outbox_available_at'), table_name='outbox')
    op.drop_table('outbox')
    op.drop_index(op.f('ix_messages_status'), table_name='messages')
    op.drop_index(op.f('ix_messages_instance_id'), table_name='messages')
    op.drop_table('messages')
    op.drop_table('media')
    op.drop_table('instances')
