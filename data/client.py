import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import asyncpg

from . import stage_event as _stage_event
from . import user_join as _user_join

logger = logging.getLogger(__name__)


class DatabaseManager:
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None

        # Supabase / Railway の DATABASE_URL を優先
        self.database_url = os.getenv("DATABASE_URL") or os.getenv(
            "DATABASE_PUBLIC_URL"
        )

        if not self.database_url:
            host = os.getenv("PGHOST") or os.getenv("DB_HOST")
            port = os.getenv("PGPORT") or os.getenv("DB_PORT", "5432")
            database = os.getenv("PGDATABASE") or os.getenv("DB_NAME", "postgres")
            user = os.getenv("PGUSER") or os.getenv("DB_USER", "postgres")
            password = os.getenv("PGPASSWORD") or os.getenv("DB_PASSWORD")

            if all([host, user, password]):
                self.database_url = (
                    f"postgresql://{user}:{password}@{host}:{port}/{database}"
                    f"?sslmode=require"
                )

    async def create_pool(self):
        """データベース接続プールを作成"""
        try:
            self.pool = await asyncpg.create_pool(
                self.database_url,
                min_size=1,
                max_size=5,
                ssl="require",
                statement_cache_size=0,
            )
            logger.info("Database connection pool created successfully")
        except Exception as e:
            logger.error(f"Failed to create database connection pool: {e}")
            raise

    async def close_pool(self):
        """データベース接続プールを閉じる"""
        if self.pool:
            await self.pool.close()
            self.pool = None
            logger.info("Database connection pool closed")

    async def initialize_tables(self):
        """必要なテーブルを初期化"""
        create_table_query = """
        CREATE TABLE IF NOT EXISTS user_joins (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            join_time TIMESTAMP WITH TIME ZONE NOT NULL,
            username VARCHAR(255),
            display_name VARCHAR(255),
            global_name VARCHAR(255),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE(user_id, join_time)
        );

        CREATE INDEX IF NOT EXISTS idx_user_joins_user ON user_joins(user_id);
        CREATE INDEX IF NOT EXISTS idx_user_joins_time ON user_joins(join_time DESC);

        CREATE TABLE IF NOT EXISTS apply_stage_coordinate (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            username VARCHAR(255),
            display_name VARCHAR(255),
            applied_period TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS fuju_users (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            username VARCHAR(255),
            display_name VARCHAR(255),
            UNIQUE(user_id)
        );

        CREATE TABLE IF NOT EXISTS fuju_balances (
            user_id BIGINT PRIMARY KEY REFERENCES fuju_users(user_id),
            amount BIGINT DEFAULT 0 CHECK (amount >= 0),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS fuju_items (
            item_id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            description TEXT,
            price BIGINT NOT NULL,
            item_type VARCHAR(50),
            duration_days INTEGER,
            stock INTEGER DEFAULT -1,
            is_active BOOLEAN DEFAULT true,
             UNIQUE(item_id)
        );

        CREATE TABLE IF NOT EXISTS fuju_transactions (
            transaction_id SERIAL PRIMARY KEY,
            user_id BIGINT REFERENCES fuju_users(user_id),
            amount BIGINT NOT NULL,
            transaction_type VARCHAR(50),
            related_item_id INTEGER REFERENCES fuju_items(item_id),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """

        if not self.pool:
            raise RuntimeError(
                "Database pool not initialized. Call create_pool() first."
            )

        async with self.pool.acquire() as connection:
            try:
                await connection.execute(create_table_query)
                logger.info("Tables initialized successfully")

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

    # --- user_join wrappers ---

    async def save_user_join(
        self,
        user_id: int,
        join_time: datetime,
        username: str = None,
        display_name: str = None,
        global_name: str = None,
    ):
        """ユーザーの参加情報をデータベースに保存"""
        return await _user_join.save_user_join(
            self.pool, user_id, join_time, username, display_name, global_name
        )

    async def get_user_join_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        """ユーザーの最新の参加情報を取得"""
        return await _user_join.get_user_join_info(self.pool, user_id)

    async def get_recent_joins(self, limit: int = 10) -> List[Dict[str, Any]]:
        """最近の参加者を取得"""
        return await _user_join.get_recent_joins(self.pool, limit)

    async def get_user_join_count(self) -> int:
        """総参加記録数を取得"""
        return await _user_join.get_user_join_count(self.pool)

    async def get_joins_by_date_range(
        self, start_date: datetime, end_date: datetime
    ) -> List[Dict[str, Any]]:
        """指定された期間の参加者を取得"""
        return await _user_join.get_joins_by_date_range(self.pool, start_date, end_date)

    async def delete_user_join_records(self, user_id: int) -> int:
        """ユーザーの参加記録を削除（管理用）"""
        return await _user_join.delete_user_join_records(self.pool, user_id)

    async def cleanup_old_records(self, days: int = 90) -> int:
        """古い記録をクリーンアップ（オプション）"""
        return await _user_join.cleanup_old_records(self.pool, days)

    async def delete_expired_joins(self) -> int:
        """join_time が1日を超えたレコードを削除する"""
        return await _user_join.delete_expired_joins(self.pool)

    # --- stage_event wrappers ---
    async def save_applied_period(
        self,
        user_id: int,
        username: str = None,
        display_name: str = None,
        applied_date: datetime = None,
    ):
        return await _stage_event.save_applied_period(
            self.pool,
            user_id,
            username,
            display_name,
            applied_date,
        )


# グローバルなデータベースマネージャーインスタンス
db_manager = DatabaseManager()
