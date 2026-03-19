import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import asyncpg

logger = logging.getLogger(__name__)


async def save_applied_period(
    pool: asyncpg.Pool,
    user_id: int,
    username: str,
    display_name: str,
    applied_date: datetime,
):
    """ユーザーの参加情報をデータベースに保存"""
    query = """
    INSERT INTO apply_stage_coordinate (user_id, username, display_name, applied_period)
    VALUES ($1, $2, $3, $4)
    RETURNING id;
    """
    async with pool.acquire() as connection:
        try:
            result = await connection.fetchval(
                query, user_id, username, display_name, applied_date
            )
            logger.info(f"Stage cordinate apply saved: user_id={user_id}")
            return result
        except Exception as e:
            logger.error(f"Failed to save apply: {e}")
            raise
