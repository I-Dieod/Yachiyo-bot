import logging
from datetime import date
from typing import List

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
