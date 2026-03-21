import logging
from datetime import date
from typing import List, Optional

import asyncpg

logger = logging.getLogger(__name__)


async def save_applied_period(
    pool: asyncpg.Pool,
    user_id: int,
    username: str,
    display_name: str,
    applied_date: date,
):
    """申請情報をデータベースに保存"""
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
            logger.info(f"Stage coordinate apply saved: user_id={user_id}")
            return result
        except Exception as e:
            logger.error(f"Failed to save apply: {e}")
            raise


async def get_due_records(
    pool: asyncpg.Pool,
    today: date,
) -> List[asyncpg.Record]:
    """applied_period が today と一致するレコードを全件取得して返す"""
    query = """
    SELECT * FROM apply_stage_coordinate
    WHERE applied_period = $1;
    """
    async with pool.acquire() as connection:
        try:
            records = await connection.fetch(query, today)
            logger.info(
                f"get_due_records: fetched {len(records)} record(s) for date={today}"
            )
            return records
        except Exception as e:
            logger.error(f"Failed to get due records: {e}")
            raise


async def get_records_before(
    pool: asyncpg.Pool,
    today: date,
) -> List[asyncpg.Record]:
    """applied_period が today より前のレコードを全件取得して返す"""
    query = """
    SELECT * FROM apply_stage_coordinate
    WHERE applied_period < $1;
    """
    async with pool.acquire() as connection:
        try:
            records = await connection.fetch(query, today)
            logger.info(
                f"get_records_before: fetched {len(records)} record(s) before date={today}"
            )
            return records
        except Exception as e:
            logger.error(f"Failed to get records before today: {e}")
            raise


async def delete_expired_records(
    pool: asyncpg.Pool,
    today: date,
) -> int:
    """applied_period が today より前のレコードを全件削除し、削除件数を返す"""
    query = """
    DELETE FROM apply_stage_coordinate
    WHERE applied_period < $1;
    """
    async with pool.acquire() as connection:
        try:
            result = await connection.execute(query, today)
            deleted_count = int(result.split()[-1])
            logger.info(
                f"delete_expired_records: deleted {deleted_count} record(s) before date={today}"
            )
            return deleted_count
        except Exception as e:
            logger.error(f"Failed to delete expired records: {e}")
            raise


async def save_review_message(
    pool: asyncpg.Pool,
    message_id: int,
    applicant_id: int,
    reason: str,
    period: date,
) -> None:
    """審査メッセージのIDと申請情報を保存する"""
    query = """
    INSERT INTO stage_review_messages (message_id, applicant_id, reason, period)
    VALUES ($1, $2, $3, $4)
    ON CONFLICT (message_id) DO NOTHING;
    """
    async with pool.acquire() as connection:
        try:
            await connection.execute(query, message_id, applicant_id, reason, period)
            logger.info(
                f"save_review_message: message_id={message_id}, applicant_id={applicant_id}"
            )
        except Exception as e:
            logger.error(f"Failed to save review message: {e}")
            raise


async def get_review_message(
    pool: asyncpg.Pool,
    message_id: int,
) -> Optional[asyncpg.Record]:
    """message_id に対応する審査メッセージレコードを1件取得する"""
    query = """
    SELECT * FROM stage_review_messages
    WHERE message_id = $1;
    """
    async with pool.acquire() as connection:
        try:
            record = await connection.fetchrow(query, message_id)
            return record
        except Exception as e:
            logger.error(f"Failed to get review message: {e}")
            raise


async def delete_review_message(
    pool: asyncpg.Pool,
    message_id: int,
) -> None:
    """message_id に対応する審査メッセージレコードを削除する"""
    query = """
    DELETE FROM stage_review_messages
    WHERE message_id = $1;
    """
    async with pool.acquire() as connection:
        try:
            await connection.execute(query, message_id)
            logger.info(f"delete_review_message: message_id={message_id}")
        except Exception as e:
            logger.error(f"Failed to delete review message: {e}")
            raise


async def get_all_review_messages(
    pool: asyncpg.Pool,
) -> List[asyncpg.Record]:
    """全審査メッセージレコードを取得する（起動時のView復元用）"""
    query = """
    SELECT * FROM stage_review_messages;
    """
    async with pool.acquire() as connection:
        try:
            records = await connection.fetch(query)
            logger.info(f"get_all_review_messages: fetched {len(records)} record(s)")
            return records
        except Exception as e:
            logger.error(f"Failed to get all review messages: {e}")
            raise
