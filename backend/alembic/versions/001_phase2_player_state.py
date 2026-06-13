"""Phase 2: Character Player State + Campaign bot_persona

Revision ID: 001_phase2_player_state
Revises: 
Create Date: 2026-06-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '001_phase2_player_state'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Campaign: add bot_persona column
    op.add_column('campaigns', sa.Column(
        'bot_persona', postgresql.JSONB(), nullable=True,
        comment='Bot人设配置: {name, personality, speaking_style, catchphrases[]}'
    ))

    # Character: add Player State columns
    op.add_column('characters', sa.Column(
        'player_qq', sa.String(32), nullable=True, index=True,
        comment='绑定玩家QQ号'
    ))
    op.add_column('characters', sa.Column(
        'sanity', sa.Integer(), nullable=True,
        comment='SAN值(理智值)'
    ))
    op.add_column('characters', sa.Column(
        'skills', postgresql.JSONB(), nullable=True,
        comment='技能表: {skill_name: value}'
    ))
    op.add_column('characters', sa.Column(
        'inventory', postgresql.JSONB(), nullable=True,
        comment='物品栏: [{name, quantity, source, note}]'
    ))
    op.add_column('characters', sa.Column(
        'personal_clues', postgresql.JSONB(), nullable=True,
        comment='个人线索: [{clue_id, content, discovered_at}]'
    ))
    op.add_column('characters', sa.Column(
        'status_effects', postgresql.JSONB(), nullable=True,
        comment='状态效果: [{name, source, remaining_rounds}]'
    ))
    op.add_column('characters', sa.Column(
        'relationships', postgresql.JSONB(), nullable=True,
        comment='人物关系: [{target_name, attitude, notes}]'
    ))
    op.add_column('characters', sa.Column(
        'state_version', sa.Integer(), nullable=True, default=0,
        comment='状态版本号,每次auto-update递增'
    ))
    op.add_column('characters', sa.Column(
        'last_modified_by', sa.String(16), nullable=True,
        comment='最后修改者: kp/auto'
    ))


def downgrade():
    op.drop_column('campaigns', 'bot_persona')
    for col in ['player_qq', 'sanity', 'skills', 'inventory',
                'personal_clues', 'status_effects', 'relationships',
                'state_version', 'last_modified_by']:
        op.drop_column('characters', col)
