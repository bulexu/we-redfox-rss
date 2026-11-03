import os
import importlib
from typing import Dict, Type
from sqlalchemy import create_engine, MetaData, inspect
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError
import logging

class DatabaseSynchronizer:
    """数据库模型同步器"""
    
    def __init__(self, db_url: str, models_dir: str = "core/models"):
        """
        初始化同步器
        
        :param db_url: 数据库连接URL
        :param models_dir: 模型目录路径
        """
        self.db_url = db_url
        self.models_dir = models_dir
        self.engine = None
        self.models = {}
        
        # 配置日志
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("Sync")
    
    def load_models(self) -> Dict[str, Type[declarative_base()]]:
        """动态加载所有模型类"""
        self.models = {}
        for filename in os.listdir(self.models_dir):
            if filename.endswith(".py") and not filename.startswith("__"):
                module_name = filename[:-3]
                try:
                    module = importlib.import_module(f"core.models.{module_name}")
                    for name, obj in module.__dict__.items():
                        if isinstance(obj, type) and hasattr(obj, "__tablename__"):
                            self.models[obj.__tablename__] = obj
                    self.logger.info(f"成功加载模型模块: {module_name}")
                except ImportError as e:
                    self.logger.warning(f"无法加载模型模块 {module_name}: {e}")
        return self.models
    
    def _map_types_for_database(self, model):
        """为不同数据库处理特殊类型映射"""
        for column in model.__table__.columns:
            type_str = str(column.type).upper()
            
            # SQLite类型映射
            if "sqlite" in self.db_url:
                # 检查多种可能的MEDIUMTEXT表示形式
                if (hasattr(column.type, "__visit_name__") and column.type.__visit_name__ == "MEDIUMTEXT") or \
                   "MEDIUMTEXT" in type_str or \
                   getattr(column.type, "__class__", None).__name__ == "MEDIUMTEXT":
                    from sqlalchemy import Text
                    column.type = Text()
                    self.logger.debug(f"已将列 {column.name} 的类型从 MEDIUMTEXT 映射为 Text")
            
            # PostgreSQL类型映射
            elif "postgresql" in self.db_url or "postgres" in self.db_url:
                # MEDIUMTEXT映射为TEXT
                if (hasattr(column.type, "__visit_name__") and column.type.__visit_name__ == "MEDIUMTEXT") or \
                   "MEDIUMTEXT" in type_str or \
                   getattr(column.type, "__class__", None).__name__ == "MEDIUMTEXT":
                    from sqlalchemy import Text
                    column.type = Text()
                    self.logger.debug(f"已将列 {column.name} 的类型从 MEDIUMTEXT 映射为 Text")
                
                # LONGTEXT映射为TEXT
                if "LONGTEXT" in type_str or \
                   getattr(column.type, "__class__", None).__name__ == "LONGTEXT":
                    from sqlalchemy import Text
                    column.type = Text()
                    self.logger.debug(f"已将列 {column.name} 的类型从 LONGTEXT 映射为 Text")
                
                # TINYINT映射为SMALLINT
                if "TINYINT" in type_str or \
                   getattr(column.type, "__class__", None).__name__ == "TINYINT":
                    from sqlalchemy import SmallInteger
                    column.type = SmallInteger()
                    self.logger.debug(f"已将列 {column.name} 的类型从 TINYINT 映射为 SmallInteger")
    
    def _check_database_permissions(self):
        """检查数据库权限"""
        try:
            with self.engine.begin() as conn:
                # 检查是否可以创建表
                if "postgresql" in self.db_url or "postgres" in self.db_url:
                    # 检查当前用户权限
                    result = conn.execute("SELECT current_user, current_database(), current_schema()")
                    user_info = result.fetchone()
                    self.logger.info(f"当前用户: {user_info[0]}, 数据库: {user_info[1]}, Schema: {user_info[2]}")
                    
                    # 检查schema权限
                    result = conn.execute("""
                        SELECT has_schema_privilege(current_user, 'public', 'CREATE') as can_create,
                               has_schema_privilege(current_user, 'public', 'USAGE') as can_use
                    """)
                    perms = result.fetchone()
                    
                    if not perms[0]:  # 没有CREATE权限
                        self.logger.error("当前用户没有在public schema中创建表的权限")
                        self.logger.info("请联系数据库管理员执行以下命令:")
                        self.logger.info(f"GRANT CREATE ON SCHEMA public TO {user_info[0]};")
                        return False
                    
                    if not perms[1]:  # 没有USAGE权限
                        self.logger.error("当前用户没有使用public schema的权限")
                        self.logger.info("请联系数据库管理员执行以下命令:")
                        self.logger.info(f"GRANT USAGE ON SCHEMA public TO {user_info[0]};")
                        return False
                        
                return True
        except Exception as e:
            self.logger.warning(f"权限检查失败: {e}")
            return True  # 如果检查失败，继续尝试

    def _migrate_cascade_task_allocations(self):
        """
        迁移 cascade_task_allocations 表：将 node_id 从 NOT NULL 改为 NULL
        SQLite 不支持 ALTER COLUMN，需要重建表
        """
        from sqlalchemy import text
        table_name = 'cascade_task_allocations'
        
        try:
            inspector = inspect(self.engine)
            if not inspector.has_table(table_name):
                return  # 表不存在，无需迁移
            
            # 检查 node_id 是否已经是 nullable
            columns = {c["name"]: c for c in inspector.get_columns(table_name)}
            if columns.get("node_id", {}).get("nullable", False):
                self.logger.info(f"{table_name}.node_id 已是 nullable，跳过迁移")
                return
            
            self.logger.info(f"开始迁移 {table_name} 表，将 node_id 改为 nullable...")
            
            with self.engine.begin() as conn:
                # 1. 创建新表
                conn.execute(text(f"""
                    CREATE TABLE {table_name}_new (
                        id VARCHAR(255) PRIMARY KEY,
                        task_id VARCHAR(255) NOT NULL,
                        task_name VARCHAR(255),
                        cron_exp VARCHAR(100),
                        node_id VARCHAR(255),
                        feed_ids TEXT NOT NULL,
                        status VARCHAR(20),
                        result_summary TEXT,
                        error_message TEXT,
                        dispatched_at DATETIME,
                        claimed_at DATETIME,
                        started_at DATETIME,
                        completed_at DATETIME,
                        schedule_run_id VARCHAR(255),
                        article_count INTEGER DEFAULT 0,
                        new_article_count INTEGER DEFAULT 0,
                        created_at DATETIME,
                        updated_at DATETIME
                    )
                """))
                
                # 2. 复制数据
                conn.execute(text(f"""
                    INSERT INTO {table_name}_new 
                    SELECT id, task_id, task_name, cron_exp, node_id, feed_ids, status,
                           result_summary, error_message, dispatched_at, claimed_at,
                           started_at, completed_at, schedule_run_id, article_count,
                           new_article_count, created_at, updated_at
                    FROM {table_name}
                """))
                
                # 3. 删除旧表
                conn.execute(text(f"DROP TABLE {table_name}"))
                
                # 4. 重命名新表
                conn.execute(text(f"ALTER TABLE {table_name}_new RENAME TO {table_name}"))
                
                # 5. 重建索引
                conn.execute(text(f"CREATE INDEX ix_{table_name}_task_id ON {table_name}(task_id)"))
                conn.execute(text(f"CREATE INDEX ix_{table_name}_node_id ON {table_name}(node_id)"))
                conn.execute(text(f"CREATE INDEX ix_{table_name}_status ON {table_name}(status)"))
                conn.execute(text(f"CREATE INDEX ix_{table_name}_schedule_run_id ON {table_name}(schedule_run_id)"))
            
            self.logger.info(f"{table_name} 表迁移完成，node_id 已改为 nullable")
            
        except Exception as e:
            self.logger.warning(f"迁移 {table_name} 表时出错: {e}")
    
    def _drop_article_lark_pushes_table(self):
        """迁移:  删除 ``article_lark_pushes`` 表 + 重置 ``lark_bitables.last_pushed_at``。

        2024 重构:  推送去重从「逐条记录」改为 ``LarkBitable.last_pushed_at``
        publish_time 水印,  ``article_lark_pushes`` 表已无用处。

        行为:
          1. 如果 ``article_lark_pushes`` 表存在,  DROP 掉;
          2. 把所有 ``lark_bitables.last_pushed_at`` 重置为 NULL,
             让升级后第一次扫描 = 「last_pushed_at 为空 → 推送全部」,
             符合新规格;  老 ``last_pushed_at`` 是 ``time.time()*1000``(当前时间
             毫秒),  远大于任何历史文章 publish_time,  会导致升级后一次都推不出去。

        幂等:  多次调用安全(先 has_table 判断,  再 UPDATE 用 IS NOT NULL 条件)。
        """
        from sqlalchemy import text
        push_table = "article_lark_pushes"
        bitable_table = "lark_bitables"
        try:
            inspector = inspect(self.engine)
            if not inspector.has_table(push_table):
                self.logger.info(f"{push_table} 表不存在,  无需删除")
            else:
                self.logger.info(f"开始迁移:  删除 {push_table} 表...")
                with self.engine.begin() as conn:
                    conn.execute(text(f"DROP TABLE IF EXISTS {push_table}"))
                self.logger.info(f"已删除 {push_table} 表")

            # 顺手把 last_pushed_at 重置为 NULL
            if inspector.has_table(bitable_table):
                # 确认 last_pushed_at 列存在再 UPDATE
                columns = {c["name"] for c in inspector.get_columns(bitable_table)}
                if "last_pushed_at" in columns:
                    with self.engine.begin() as conn:
                        result = conn.execute(
                            text(
                                f"UPDATE {bitable_table} "
                                f"SET last_pushed_at = NULL "
                                f"WHERE last_pushed_at IS NOT NULL"
                            )
                        )
                        self.logger.info(
                            f"重置 {bitable_table}.last_pushed_at: {result.rowcount} 行"
                        )
                else:
                    self.logger.info(
                        f"{bitable_table} 没有 last_pushed_at 列,  跳过重置"
                    )
            else:
                self.logger.info(f"{bitable_table} 表不存在,  跳过重置 last_pushed_at")
        except Exception as e:
            self.logger.warning(f"迁移 article_lark_pushes 时出错(已忽略):  {e}")

    def _migrate_articles_updated_at_millis(self):
        """
        迁移 articles 表：将 updated_at_millis 从 INT 改为 BIGINT
        解决毫秒时间戳超出 INT 范围的问题
        """
        from sqlalchemy import text
        table_name = 'articles'
        
        try:
            inspector = inspect(self.engine)
            if not inspector.has_table(table_name):
                return  # 表不存在，无需迁移
            
            columns = {c["name"]: c for c in inspector.get_columns(table_name)}
            col_info = columns.get("updated_at_millis")
            
            if not col_info:
                return  # 列不存在
            
            # 检查是否已经是 BIGINT
            col_type = str(col_info.get("type", "")).upper()
            if "BIGINT" in col_type or "BIG" in col_type:
                self.logger.info(f"{table_name}.updated_at_millis 已是 BIGINT，跳过迁移")
                return
            
            self.logger.info(f"开始迁移 {table_name} 表，将 updated_at_millis 改为 BIGINT...")
            
            with self.engine.begin() as conn:
                if "mysql" in self.db_url:
                    # MySQL 直接修改列类型
                    conn.execute(text(f"ALTER TABLE {table_name} MODIFY COLUMN updated_at_millis BIGINT"))
                    self.logger.info(f"{table_name}.updated_at_millis 已改为 BIGINT")
                elif "postgresql" in self.db_url or "postgres" in self.db_url:
                    # PostgreSQL
                    conn.execute(text(f'ALTER TABLE "{table_name}" ALTER COLUMN updated_at_millis TYPE BIGINT'))
                    self.logger.info(f"{table_name}.updated_at_millis 已改为 BIGINT")
                else:
                    # SQLite 不支持 ALTER COLUMN，跳过（新表会自动使用正确类型）
                    self.logger.info(f"SQLite 不支持 ALTER COLUMN，跳过迁移")
            
        except Exception as e:
            self.logger.warning(f"迁移 {table_name}.updated_at_millis 时出错: {e}")

    def _migrate_feed_id_rename(self):
        """2024 重构: 多平台订阅统一 ``feed_id`` 命名。

        行为:
          1. ``articles.mp_id``         → ``articles.feed_id``
          2. ``message_tasks.mps_id``   → ``message_tasks.target_feed_ids``
          3. ``message_tasks`` 添加 ``platform VARCHAR(20) DEFAULT 'wechat'``,
             历史行回填 ``'wechat'``。

        SQLite < 3.25 不支持 ``ALTER TABLE ... RENAME COLUMN``,  走
        ``_sqlite_rebuild_table_with_rename`` 重建表方案。

        幂等:  多次调用安全 (用 has_column 判断,  RENAME 时检查源列在且目标列不在)。
        """
        from sqlalchemy import text

        inspector = inspect(self.engine)
        is_sqlite = "sqlite" in self.db_url

        def _has_column(table, col):
            return inspector.has_table(table) and col in {
                c["name"] for c in inspector.get_columns(table)
            }

        # 1. articles.mp_id → feed_id
        if _has_column("articles", "mp_id") and not _has_column("articles", "feed_id"):
            self.logger.info("迁移 articles.mp_id → feed_id")
            try:
                with self.engine.begin() as conn:
                    if is_sqlite:
                        try:
                            conn.execute(text(
                                "ALTER TABLE articles RENAME COLUMN mp_id TO feed_id"
                            ))
                        except SQLAlchemyError:
                            self._sqlite_rebuild_table_with_rename(
                                "articles", "mp_id", "feed_id",
                            )
                    else:
                        conn.execute(text(
                            "ALTER TABLE articles RENAME COLUMN mp_id TO feed_id"
                        ))
                self.logger.info("articles.mp_id → feed_id 完成")
            except Exception as exc:  # noqa: BLE001
                self.logger.warning(f"迁移 articles.mp_id 时出错: {exc}")

        # 2. message_tasks.mps_id → target_feed_ids
        if _has_column("message_tasks", "mps_id") and not _has_column(
            "message_tasks", "target_feed_ids"
        ):
            self.logger.info("迁移 message_tasks.mps_id → target_feed_ids")
            try:
                with self.engine.begin() as conn:
                    if is_sqlite:
                        try:
                            conn.execute(text(
                                "ALTER TABLE message_tasks RENAME COLUMN mps_id TO target_feed_ids"
                            ))
                        except SQLAlchemyError:
                            self._sqlite_rebuild_table_with_rename(
                                "message_tasks", "mps_id", "target_feed_ids",
                            )
                    else:
                        conn.execute(text(
                            "ALTER TABLE message_tasks RENAME COLUMN mps_id TO target_feed_ids"
                        ))
                self.logger.info("message_tasks.mps_id → target_feed_ids 完成")
            except Exception as exc:  # noqa: BLE001
                self.logger.warning(f"迁移 message_tasks.mps_id 时出错: {exc}")

        # 3. message_tasks.platform (DEFAULT 'wechat',  历史行回填)
        if _has_column("message_tasks", "id") and not _has_column(
            "message_tasks", "platform"
        ):
            self.logger.info("添加 message_tasks.platform 列")
            try:
                with self.engine.begin() as conn:
                    if is_sqlite:
                        conn.execute(text(
                            "ALTER TABLE message_tasks ADD COLUMN platform VARCHAR(20) DEFAULT 'wechat'"
                        ))
                    elif "postgresql" in self.db_url or "postgres" in self.db_url:
                        conn.execute(text(
                            'ALTER TABLE "message_tasks" ADD COLUMN "platform" VARCHAR(20) DEFAULT \'wechat\''
                        ))
                    else:
                        conn.execute(text(
                            "ALTER TABLE message_tasks ADD COLUMN platform VARCHAR(20) DEFAULT 'wechat'"
                        ))
                # 回填历史 NULL 行
                with self.engine.begin() as conn:
                    conn.execute(text(
                        "UPDATE message_tasks SET platform = 'wechat' WHERE platform IS NULL"
                    ))
                self.logger.info("message_tasks.platform 列添加完成")
            except Exception as exc:  # noqa: BLE001
                self.logger.warning(f"添加 message_tasks.platform 列时出错: {exc}")

        # 4. lark_bitables.mp_ids → feed_ids (改名)
        if _has_column("lark_bitables", "mp_ids") and not _has_column(
            "lark_bitables", "feed_ids"
        ):
            self.logger.info("迁移 lark_bitables.mp_ids → feed_ids")
            try:
                with self.engine.begin() as conn:
                    if is_sqlite:
                        try:
                            conn.execute(text(
                                "ALTER TABLE lark_bitables RENAME COLUMN mp_ids TO feed_ids"
                            ))
                        except SQLAlchemyError:
                            self._sqlite_rebuild_table_with_rename(
                                "lark_bitables", "mp_ids", "feed_ids",
                            )
                    else:
                        conn.execute(text(
                            "ALTER TABLE lark_bitables RENAME COLUMN mp_ids TO feed_ids"
                        ))
                self.logger.info("lark_bitables.mp_ids → feed_ids 完成")
            except Exception as exc:  # noqa: BLE001
                self.logger.warning(f"迁移 lark_bitables.mp_ids 时出错: {exc}")

        # 5. tags.mps_id → feed_ids (改名)
        if _has_column("tags", "mps_id") and not _has_column("tags", "feed_ids"):
            self.logger.info("迁移 tags.mps_id → feed_ids")
            try:
                with self.engine.begin() as conn:
                    if is_sqlite:
                        try:
                            conn.execute(text(
                                "ALTER TABLE tags RENAME COLUMN mps_id TO feed_ids"
                            ))
                        except SQLAlchemyError:
                            self._sqlite_rebuild_table_with_rename(
                                "tags", "mps_id", "feed_ids",
                            )
                    else:
                        conn.execute(text(
                            "ALTER TABLE tags RENAME COLUMN mps_id TO feed_ids"
                        ))
                self.logger.info("tags.mps_id → feed_ids 完成")
            except Exception as exc:  # noqa: BLE001
                self.logger.warning(f"迁移 tags.mps_id 时出错: {exc}")

        # 6. filter_rules.mp_id → feed_id (改名)
        if _has_column("filter_rules", "mp_id") and not _has_column(
            "filter_rules", "feed_id"
        ):
            self.logger.info("迁移 filter_rules.mp_id → feed_id")
            try:
                with self.engine.begin() as conn:
                    if is_sqlite:
                        try:
                            conn.execute(text(
                                "ALTER TABLE filter_rules RENAME COLUMN mp_id TO feed_id"
                            ))
                        except SQLAlchemyError:
                            self._sqlite_rebuild_table_with_rename(
                                "filter_rules", "mp_id", "feed_id",
                            )
                    else:
                        conn.execute(text(
                            "ALTER TABLE filter_rules RENAME COLUMN mp_id TO feed_id"
                        ))
                self.logger.info("filter_rules.mp_id → feed_id 完成")
            except Exception as exc:  # noqa: BLE001
                self.logger.warning(f"迁移 filter_rules.mp_id 时出错: {exc}")

        # 7. feeds.mp_name → name, mp_cover → cover, mp_intro → intro (改名)
        for old_col, new_col in [
            ("mp_name", "name"),
            ("mp_cover", "cover"),
            ("mp_intro", "intro"),
        ]:
            if _has_column("feeds", old_col) and not _has_column("feeds", new_col):
                self.logger.info(f"迁移 feeds.{old_col} → {new_col}")
                try:
                    with self.engine.begin() as conn:
                        if is_sqlite:
                            try:
                                conn.execute(text(
                                    f"ALTER TABLE feeds RENAME COLUMN {old_col} TO {new_col}"
                                ))
                            except SQLAlchemyError:
                                self._sqlite_rebuild_table_with_rename(
                                    "feeds", old_col, new_col,
                                )
                        else:
                            conn.execute(text(
                                f"ALTER TABLE feeds RENAME COLUMN {old_col} TO {new_col}"
                            ))
                    self.logger.info(f"feeds.{old_col} → {new_col} 完成")
                except Exception as exc:  # noqa: BLE001
                    self.logger.warning(f"迁移 feeds.{old_col} 时出错: {exc}")

        # 7b. feeds 旧列 (mp_name/mp_cover/mp_intro) 与新列同时存在的兜底:
        #     现象 — SQLAlchemy 启动时已根据新 model 自动创建 ``name``/``cover``/``intro``
        #     三列 (旧数据并未迁移),  第 7 步因 ``new_col`` 已存在被跳过,  导致
        #     /api/v1/mps 返回的 name/cover/intro 全部为 NULL。
        #     处理:
        #       1. 把 ``mp_name`` 的非空数据复制到 ``name`` (同名 ``mp_cover``/``mp_intro``
        #          处理同理)。
        #       2. 复制完成后 ``mp_name`` 已无存在价值,  DROP COLUMN。
        #     兼容 SQLite 3.35+ (DROP COLUMN 原生支持) 与 PG/MySQL。
        for old_col, new_col in [
            ("mp_name", "name"),
            ("mp_cover", "cover"),
            ("mp_intro", "intro"),
        ]:
            if _has_column("feeds", old_col) and _has_column("feeds", new_col):
                self.logger.info(
                    f"feeds 同时存在 {old_col} + {new_col},  触发兜底迁移"
                )
                try:
                    with self.engine.begin() as conn:
                        # 1) 复制非空数据 (只在 new_col 为 NULL 时覆盖,  避免
                        #    用户已经在新列手动改过的值被覆盖)
                        conn.execute(text(
                            f"UPDATE feeds SET {new_col} = {old_col} "
                            f"WHERE {new_col} IS NULL AND {old_col} IS NOT NULL"
                        ))
                        # 2) DROP 旧列
                        if is_sqlite:
                            conn.execute(text(
                                f"ALTER TABLE feeds DROP COLUMN {old_col}"
                            ))
                        else:
                            conn.execute(text(
                                f"ALTER TABLE feeds DROP COLUMN {old_col}"
                            ))
                        # 3) 重建索引 (SQLAlchemy 不会自动重建已存在但失去
                        #    底层列的索引,  防止 index 引用不存在的列报错)
                        try:
                            conn.execute(text(
                                f"DROP INDEX IF EXISTS ix_feeds_{old_col}"
                            ))
                        except SQLAlchemyError:
                            pass
                    self.logger.info(
                        f"feeds.{old_col} 数据已迁移至 {new_col} 并 DROP"
                    )
                except Exception as exc:  # noqa: BLE001
                    self.logger.warning(
                        f"feeds.{old_col} → {new_col} 兜底迁移时出错: {exc}"
                    )

    def _sqlite_rebuild_table_with_rename(self, table_name: str, old_col: str, new_col: str):
        """SQLite 旧版本重建表并重命名列。

        通用方案:  CREATE 新表 → 复制数据 → DROP 旧表 → RENAME 新表 → 重建索引。
        列定义从 SQLAlchemy model 反射读取。
        """
        from sqlalchemy import text

        if "sqlite" not in self.db_url:
            raise RuntimeError("仅 SQLite 需要重建表")

        model = self.models.get(table_name)
        if model is None:
            # fallback: 通过 metadata 反射
            model = next(
                (m for m in self.models.values() if m.__tablename__ == table_name),
                None,
            )
        if model is None:
            raise RuntimeError(f"找不到表 {table_name} 对应的 SQLAlchemy model")

        # 构造 CREATE TABLE 语句
        col_defs = []
        for col in model.__table__.columns:
            name = col.name
            # 旧列名替换成新列名
            type_str = str(col.type)
            nullable = "" if col.nullable else " NOT NULL"
            default = ""
            if col.default is not None and hasattr(col.default, "arg"):
                arg = col.default.arg
                if isinstance(arg, (int, float)):
                    default = f" DEFAULT {arg}"
                elif isinstance(arg, str):
                    default = f" DEFAULT '{arg}'"
            pk = " PRIMARY KEY" if col.primary_key else ""
            col_defs.append(f'"{name}" {type_str}{nullable}{default}{pk}')

        create_sql = f'CREATE TABLE {table_name}_new ({", ".join(col_defs)})'

        # 列出所有列(以旧列名作为源), 在 SELECT 时做 rename
        all_cols = [c.name for c in model.__table__.columns]
        col_list = ", ".join(f'"{c}"' for c in all_cols)
        insert_sql = f'INSERT INTO {table_name}_new ({col_list}) SELECT {col_list} FROM {table_name}'

        with self.engine.begin() as conn:
            conn.execute(text(create_sql))
            conn.execute(text(insert_sql))
            conn.execute(text(f"DROP TABLE {table_name}"))
            conn.execute(text(f"ALTER TABLE {table_name}_new RENAME TO {table_name}"))
            # 重建索引(从 model 反射)
            for idx in model.__table__.indexes:
                cols = ", ".join(f'"{c.name}"' for c in idx.columns)
                idx_name = idx.name or f"ix_{table_name}_{'_'.join(c.name for c in idx.columns)}"
                conn.execute(text(f'CREATE INDEX IF NOT EXISTS "{idx_name}" ON {table_name} ({cols})'))
    
    def sync(self):
        """同步模型到数据库"""
        try:
            self.engine = create_engine(self.db_url)
            
            # 检查数据库权限
            if not self._check_database_permissions():
                return False
            
            metadata = MetaData()
            
            # 反射现有数据库结构
            metadata.reflect(bind=self.engine)
            
            # SQLite 特殊迁移：修改 node_id 为 nullable
            if "sqlite" in self.db_url:
                self._migrate_cascade_task_allocations()

            # MySQL/PostgreSQL 迁移：修改 updated_at_millis 为 BIGINT
            self._migrate_articles_updated_at_millis()

            # 2024 重构:  删除已废弃的 article_lark_pushes 表,  重置 last_pushed_at
            self._drop_article_lark_pushes_table()

            # 2024 重构:  Article.mp_id → Article.feed_id + MessageTask.mps_id → MessageTask.target_feed_ids + MessageTask.platform 列
            self._migrate_feed_id_rename()
            
            # 处理不同数据库的特殊类型映射
            for model in self.models.values():
                self._map_types_for_database(model)
            
            # 加载模型
            if not self.models:
                self.load_models()
                if not self.models:
                    self.logger.error("没有找到任何模型类")
                    return False
            
            # 为不同数据库类型处理自增主键
            if "sqlite" in self.db_url:
                # SQLite使用AUTOINCREMENT
                pass  # SQLAlchemy默认处理
            elif "mysql" in self.db_url:
                # MySQL使用AUTO_INCREMENT
                pass  # SQLAlchemy默认处理
            elif "postgresql" in self.db_url or "postgres" in self.db_url:
                # PostgreSQL使用SERIAL或IDENTITY
                pass  # SQLAlchemy默认处理
            
            # 创建或更新表结构
            for model in self.models.values():
                table_name = model.__tablename__
                inspector = inspect(self.engine)
                
                try:
                    if not inspector.has_table(table_name):
                        # 尝试创建表
                        model.metadata.create_all(self.engine)
                        self.logger.info(f"创建表: {table_name}")
                    else:
                        # 检查字段差异并更新表
                        existing_columns = {c["name"]: c for c in inspector.get_columns(table_name)}
                        model_columns = {c.name: c for c in model.__table__.columns}
                        
                        # 检查新增或修改的字段
                        for col_name, model_col in model_columns.items():
                            if col_name not in existing_columns:
                                # 新增字段 - 根据数据库类型调整语法
                                from sqlalchemy import text
                                try:
                                    with self.engine.begin() as conn:
                                        if "postgresql" in self.db_url or "postgres" in self.db_url:
                                            # PostgreSQL语法
                                            conn.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN "{col_name}" {model_col.type}'))
                                        else:
                                            # SQLite和MySQL语法
                                            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {model_col.type}"))
                                    self.logger.info(f"新增字段: {table_name}.{col_name}")
                                except SQLAlchemyError as e:
                                    self.logger.error(f"添加字段 {table_name}.{col_name} 失败: {e}")
                        
                        self.logger.info(f"表已同步: {table_name}")
                        
                except SQLAlchemyError as e:
                    self.logger.error(f"处理表 {table_name} 时出错: {e}")
                    if "permission denied" in str(e).lower():
                        self.logger.error("权限不足，请检查数据库用户权限")
                        return False
                    continue
            
            self.logger.info("模型同步完成")
            return True
        except SQLAlchemyError as e:
            self.logger.error(f"数据库同步失败: {e}")
            if "permission denied" in str(e).lower():
                self.logger.error("数据库权限不足，请检查以下几点:")
                self.logger.error("1. 确保数据库用户有CREATE权限")
                self.logger.error("2. 确保数据库用户有USAGE权限")
                self.logger.error("3. 如果是PostgreSQL，请联系管理员执行权限授予命令")
            return False
        except Exception as e:
            self.logger.error(f"同步过程中发生未知错误: {e}")
            return False
        finally:
            if self.engine:
                self.engine.dispose()

def main():
    # 示例使用 - 支持多种数据库
    # SQLite
    # synchronizer = DatabaseSynchronizer(db_url="sqlite:///data/db.db")
    
    # PostgreSQL
    # synchronizer = DatabaseSynchronizer(db_url="postgresql://username:password@localhost:5432/dbname")
    
    # MySQL
    # synchronizer = DatabaseSynchronizer(db_url="mysql+pymysql://username:password@localhost:3306/dbname")
    from core.config import cfg
    db_url=cfg.get("db","sqlite:///data/db.db")
    synchronizer = DatabaseSynchronizer(db_url=db_url)
    synchronizer.sync()

if __name__ == "__main__":
    main()