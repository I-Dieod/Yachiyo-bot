import asyncio
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import asyncpg

logger = logging.getLogger(__name__)


class DatabaseManager:
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None

        # Railway provides multiple database URL options
        self.database_url = os.getenv("DATABASE_URL") or os.getenv(
            "DATABASE_PUBLIC_URL"
        )

        # Fallback to individual Railway environment variables if DATABASE_URL is not set
        if not self.database_url:
            host = os.getenv("PGHOST")
            port = os.getenv("PGPORT", "5432")
            database = os.getenv("PGDATABASE", "railway")
            user = os.getenv("PGUSER", "postgres")
            password = os.getenv("PGPASSWORD")

            # Additional fallback to legacy environment variables
            if not all([host, user, password]):
                host = host or os.getenv("DB_HOST")
                port = port or os.getenv("DB_PORT", "5432")
                database = database or os.getenv("DB_NAME", "railway")
                user = user or os.getenv("DB_USER", "postgres")
                password = password or os.getenv("DB_PASSWORD")

            if all([host, user, password]):
                self.database_url = f"postgresql://{user}:{password}@{host}:{port}/{database}?sslmode=require"

    async def create_pool(self):
        """データベース接続プールを作成"""
        if not self.database_url:
            raise ValueError(
                "Database connection string not found. Please set DATABASE_URL, DATABASE_PUBLIC_URL, or individual PG* environment variables."
            )

        try:
            # Log connection attempt (without exposing password)
            safe_url = self.database_url
            if "@" in safe_url:
                # Hide password in logs: postgresql://user:***@host:port/db
                parts = safe_url.split("@")
                user_part = parts[0].split(":")
                if len(user_part) >= 3:
                    user_part[2] = "***"
                safe_url = ":".join(user_part) + "@" + parts[1]

            logger.info(f"Attempting to connect to database: {safe_url}")

            self.pool = await asyncpg.create_pool(
                self.database_url,
                min_size=1,
                max_size=10,
                command_timeout=60,
                server_settings={"application_name": "yachiyo_bot"},
            )
            logger.info("Database connection pool created successfully")

            # Test the connection
            async with self.pool.acquire() as connection:
                result = await connection.fetchval("SELECT version()")
                logger.info(f"Connected to PostgreSQL: {result}")

        except Exception as e:
            logger.error(f"Failed to create database connection pool: {e}")
            logger.error(
                f"Connection URL format: {safe_url if 'safe_url' in locals() else 'Unable to parse URL'}"
            )
            raise

    async def close_pool(self):
        """データベース接続プールを閉じる"""
        if self.pool:
            await self.pool.close()
            logger.info("Database connection pool closed")

    async def initialize_tables(self):
        """必要なテーブルを初期化"""
        create_table_query = """
        CREATE TABLE IF NOT EXISTS user_joins (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            guild_id BIGINT NOT NULL,
            join_time TIMESTAMP WITH TIME ZONE NOT NULL,
            username VARCHAR(255),
            display_name VARCHAR(255),
            global_name VARCHAR(255),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE(user_id, guild_id, join_time)
        );

        CREATE INDEX IF NOT EXISTS idx_user_joins_user_guild ON user_joins(user_id, guild_id);
        CREATE INDEX IF NOT EXISTS idx_user_joins_guild_time ON user_joins(guild_id, join_time DESC);
        CREATE INDEX IF NOT EXISTS idx_user_joins_time ON user_joins(join_time DESC);
        """

        if not self.pool:
            raise RuntimeError(
                "Database pool not initialized. Call create_pool() first."
            )

        async with self.pool.acquire() as connection:
            try:
                await connection.execute(create_table_query)
                logger.info("Tables initialized successfully")

                # Verify table creation
                table_exists = await connection.fetchval(
                    "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'user_joins')"
                )
                if table_exists:
                    logger.info("user_joins table verified")
                else:
                    logger.warning(
                        "user_joins table may not have been created properly"
                    )

            except Exception as e:
                logger.error(f"Failed to initialize tables: {e}")
                raise

    async def save_user_join(
        self,
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

        async with self.pool.acquire() as connection:
            try:
                result = await connection.fetchval(
                    query,
                    user_id,
                    guild_id,
                    join_time,
                    username,
                    display_name,
                    global_name,
                )
                logger.info(f"User join saved: user_id={user_id}, guild_id={guild_id}")
                return result
            except Exception as e:
                logger.error(f"Failed to save user join: {e}")
                raise

    async def get_user_join_info(
        self, user_id: int, guild_id: int
    ) -> Optional[Dict[str, Any]]:
        """ユーザーの最新の参加情報を取得"""
        query = """
        SELECT user_id, guild_id, join_time, username, display_name, global_name, created_at
        FROM user_joins
        WHERE user_id = $1 AND guild_id = $2
        ORDER BY join_time DESC
        LIMIT 1;
        """

        async with self.pool.acquire() as connection:
            try:
                row = await connection.fetchrow(query, user_id, guild_id)
                if row:
                    return dict(row)
                return None
            except Exception as e:
                logger.error(f"Failed to get user join info: {e}")
                return None

    async def get_recent_joins(
        self, guild_id: int, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """指定されたギルドの最近の参加者を取得"""
        query = """
        SELECT user_id, guild_id, join_time, username, display_name, global_name, created_at
        FROM user_joins
        WHERE guild_id = $1
        ORDER BY join_time DESC
        LIMIT $2;
        """

        async with self.pool.acquire() as connection:
            try:
                rows = await connection.fetch(query, guild_id, limit)
                return [dict(row) for row in rows]
            except Exception as e:
                logger.error(f"Failed to get recent joins: {e}")
                return []

    async def get_user_join_count(self, guild_id: int) -> int:
        """指定されたギルドの総参加記録数を取得"""
        query = "SELECT COUNT(*) FROM user_joins WHERE guild_id = $1;"

        async with self.pool.acquire() as connection:
            try:
                return await connection.fetchval(query, guild_id)
            except Exception as e:
                logger.error(f"Failed to get user join count: {e}")
                return 0

    async def get_joins_by_date_range(
        self, guild_id: int, start_date: datetime, end_date: datetime
    ) -> List[Dict[str, Any]]:
        """指定された期間の参加者を取得"""
        query = """
        SELECT user_id, guild_id, join_time, username, display_name, global_name, created_at
        FROM user_joins
        WHERE guild_id = $1 AND join_time BETWEEN $2 AND $3
        ORDER BY join_time DESC;
        """

        async with self.pool.acquire() as connection:
            try:
                rows = await connection.fetch(query, guild_id, start_date, end_date)
                return [dict(row) for row in rows]
            except Exception as e:
                logger.error(f"Failed to get joins by date range: {e}")
                return []

    async def delete_user_join_records(self, user_id: int, guild_id: int) -> int:
        """ユーザーの参加記録を削除（管理用）"""
        query = "DELETE FROM user_joins WHERE user_id = $1 AND guild_id = $2;"

        async with self.pool.acquire() as connection:
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

    async def cleanup_old_records(self, days: int = 90) -> int:
        """古い記録をクリーンアップ（オプション）"""
        query = """
        DELETE FROM user_joins
        WHERE created_at < NOW() - INTERVAL '%s days';
        """

        async with self.pool.acquire() as connection:
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


# グローバルなデータベースマネージャーインスタンス
db_manager = DatabaseManager()
