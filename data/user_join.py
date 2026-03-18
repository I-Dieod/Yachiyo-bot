import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import asyncpg

logger = logging.getLogger(__name__)


async def save_user_join(
    pool: asyncpg.Pool,
    user_id: int,
    guild_id: int,
    join_time: datetime,
    username: str = None,
    display_name: str = None,
    global_name: str = None,
):
    """ユーザーの参加情報をデータベースに保存"""
    query = """
    INSERT INTO user_joins (user_id, guild_id, join_time, username, display_name, global_name)
    VALUES ($1, $2, $3, $4, $5, $6)
    ON CONFLICT (user_id, guild_id, join_time) DO UPDATE SET
        username = EXCLUDED.username,
        display_name = EXCLUDED.display_name,
        global_name = EXCLUDED.global_name
    RETURNING id;
    """
    async with pool.acquire() as connection:
        try:
            result = await connection.fetchval(
                query, user_id, guild_id, join_time, username, display_name, global_name
            )
            logger.info(f"User join saved: user_id={user_id}, guild_id={guild_id}")
            return result
        except Exception as e:
            logger.error(f"Failed to save user join: {e}")
            raise


async def get_user_join_info(
    pool: asyncpg.Pool, user_id: int, guild_id: int
) -> Optional[Dict[str, Any]]:
    """ユーザーの最新の参加情報を取得"""
    query = """
    SELECT user_id, guild_id, join_time, username, display_name, global_name, created_at
    FROM user_joins
    WHERE user_id = $1 AND guild_id = $2
    ORDER BY join_time DESC
    LIMIT 1;
    """
    async with pool.acquire() as connection:
        try:
            row = await connection.fetchrow(query, user_id, guild_id)
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get user join info: {e}")
            return None


async def get_recent_joins(
    pool: asyncpg.Pool, guild_id: int, limit: int = 10
) -> List[Dict[str, Any]]:
    """指定されたギルドの最近の参加者を取得"""
    query = """
    SELECT user_id, guild_id, join_time, username, display_name, global_name, created_at
    FROM user_joins
    WHERE guild_id = $1
    ORDER BY join_time DESC
    LIMIT $2;
    """
    async with pool.acquire() as connection:
        try:
            rows = await connection.fetch(query, guild_id, limit)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get recent joins: {e}")
            return []


async def get_user_join_count(pool: asyncpg.Pool, guild_id: int) -> int:
    """指定されたギルドの総参加記録数を取得"""
    query = "SELECT COUNT(*) FROM user_joins WHERE guild_id = $1;"
    async with pool.acquire() as connection:
        try:
            return await connection.fetchval(query, guild_id)
        except Exception as e:
            logger.error(f"Failed to get user join count: {e}")
            return 0


async def get_joins_by_date_range(
    pool: asyncpg.Pool,
    guild_id: int,
    start_date: datetime,
    end_date: datetime,
) -> List[Dict[str, Any]]:
    """指定された期間の参加者を取得"""
    query = """
    SELECT user_id, guild_id, join_time, username, display_name, global_name, created_at
    FROM user_joins
    WHERE guild_id = $1 AND join_time BETWEEN $2 AND $3
    ORDER BY join_time DESC;
    """
    async with pool.acquire() as connection:
        try:
            rows = await connection.fetch(query, guild_id, start_date, end_date)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get joins by date range: {e}")
            return []


async def delete_user_join_records(
    pool: asyncpg.Pool, user_id: int, guild_id: int
) -> int:
    """ユーザーの参加記録を削除（管理用）"""
    query = "DELETE FROM user_joins WHERE user_id = $1 AND guild_id = $2;"
    async with pool.acquire() as connection:
        try:
            result = await connection.execute(query, user_id, guild_id)
            deleted_count = int(result.split()[-1])
            logger.info(
                f"Deleted {deleted_count} join records for user {user_id} in guild {guild_id}"
            )
            return deleted_count
        except Exception as e:
            logger.error(f"Failed to delete user join records: {e}")
            return 0


async def cleanup_old_records(pool: asyncpg.Pool, days: int = 90) -> int:
    """古い記録をクリーンアップ（オプション）"""
    query = """
    DELETE FROM user_joins
    WHERE created_at < NOW() - INTERVAL '%s days';
    """
    async with pool.acquire() as connection:
        try:
            result = await connection.execute(query % days)
            deleted_count = int(result.split()[-1])
            logger.info(
                f"Cleaned up {deleted_count} old join records (older than {days} days)"
            )
            return deleted_count
        except Exception as e:
            logger.error(f"Failed to cleanup old records: {e}")
            return 0
