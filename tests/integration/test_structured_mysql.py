import copy
import json
import re
import sys
import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import event, func, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))
from biz_aid_pipeline.bizinfo.models import SourceBatch, SourcePage, SyncScope
from biz_aid_pipeline.config.settings import DbConfig, PipelineError
from biz_aid_pipeline.ingestion.service import ingest
from biz_aid_pipeline.persistence.mysql_repository import MysqlRepository, utc_datetime
sys.path.insert(0, str(ROOT / "scripts/lib"))
from validate import database_comments


class StructuredMysqlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 임시 fixture는 별도 dev test DB만 사용한다. 실제 Pilot과 prod는 테스트 초기화 대상이 아니다.
        cls.repository = MysqlRepository(replace(DbConfig.load(ROOT, "dev"), database="biz_aid_test"))
        cls.fixture = json.loads((ROOT / "tests/fixtures/external-api/bizinfo-user-sample.json").read_bytes())["response"]["body"]["items"]["item"]

    @classmethod
    def tearDownClass(cls):
        cls.repository.close()

    def setUp(self):
        self.prefix = "TEST_" + uuid.uuid4().hex[:16]
        self.base = [{"pblancId": self.prefix + "_A", "pblancNm": "합성 A", "reqstBeginEndDe": "2026-09-01 ~ 2026-09-30"},
                     {"pblancId": self.prefix + "_B", "pblancNm": "합성 B", "reqstBeginEndDe": "예산 소진시까지"}]

    def data(self, items=None, scope=SyncScope.SAMPLE, total=None):
        items = self.base if items is None else items
        return SourceBatch(scope, (SourcePage(1, max(1, len(items)), tuple(items), len(items) if total is None else total),), "controlled fixture", True)

    def run_data(self, data=None):
        return ingest(self.repository, self.data() if data is None else data, "test-" + uuid.uuid4().hex)

    def row(self, identifier=None):
        with self.repository.engine.connect() as connection:
            return connection.execute(select(self.repository.programs).where(
                self.repository.programs.c.pblanc_id == (identifier or self.base[0]["pblancId"]))).mappings().first()

    def count(self):
        with self.repository.engine.connect() as connection:
            return connection.execute(select(func.count()).select_from(self.repository.programs)).scalar_one()

    def test_insert(self):
        report = self.run_data()
        self.assertEqual((report["status"], report["inserted"], report["failed"]), ("PASS", 2, 0))
        self.assertEqual(self.row()["source_payload"], self.base[0])
        self.assertEqual(str(self.row()["application_start_date"]), "2026-09-01")

    def test_date_refresh_only_derived_columns_and_idempotent(self):
        from biz_aid_pipeline.ingestion.date_refresh import refresh_dates
        items = [dict(self.base[0], reqstBeginEndDe="2026.01.02 ~ 2026.10.03")]
        self.run_data(self.data(items))
        table = self.repository.programs
        with self.repository.engine.begin() as connection:
            connection.execute(update(table).where(table.c.pblanc_id == items[0]["pblancId"]).values(
                application_start_date=None, application_end_date=None))
        before = dict(self.row())
        refresh_dates(self.repository, True)
        after = dict(self.row())
        self.assertEqual(str(after.pop("application_start_date")), "2026-01-02")
        self.assertEqual(str(after.pop("application_end_date")), "2026-10-03")
        before.pop("application_start_date")
        before.pop("application_end_date")
        self.assertEqual(after, before)
        self.assertEqual(refresh_dates(self.repository, True)["changed_rows"], 0)

    def test_actual_dev_mysql_port_3306(self):
        self.assertEqual(self.repository.engine.url.port, 3306)
        with self.repository.engine.connect() as connection:
            self.assertEqual(connection.execute(text("SELECT @@port")).scalar_one(), 3306)

    def test_database_unique_key(self):
        self.run_data()
        row = dict(self.row())
        row.pop("id")
        with self.assertRaises(IntegrityError), self.repository.engine.begin() as connection:
            connection.execute(self.repository.programs.insert().values(**row))

    def test_noop_content_not_updated(self):
        self.run_data()
        before = self.row()
        statements = []
        def capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)
        event.listen(self.repository.engine, "before_cursor_execute", capture)
        try:
            report = self.run_data()
        finally:
            event.remove(self.repository.engine, "before_cursor_execute", capture)
        self.assertEqual((report["inserted"], report["updated"], report["noop"]), (0, 0, 2))
        after = self.row()
        self.assertEqual(after["updated_at"], before["updated_at"])
        self.assertGreaterEqual(after["last_seen_at"], before["last_seen_at"])
        updates = [s for s in statements if s.startswith("UPDATE support_programs ")]
        self.assertTrue(updates)
        self.assertTrue(all("source_payload=" not in s and "source_fingerprint=" not in s and "name=" not in s for s in updates))

    def test_exact_one_changed_source(self):
        self.run_data()
        changed = copy.deepcopy(self.base)
        changed[0]["pblancNm"] = "정확히 한 필드만 변경"
        report = self.run_data(self.data(changed))
        self.assertEqual((report["updated"], report["noop"], report["inserted"]), (1, 1, 0))
        self.assertEqual(self.row()["name"], changed[0]["pblancNm"])

    def test_reactivation_same_content(self):
        self.run_data()
        with self.repository.engine.begin() as connection:
            connection.execute(update(self.repository.programs).where(self.repository.programs.c.pblanc_id == self.base[0]["pblancId"])
                .values(source_active=False, source_deleted=True, source_deleted_at=utc_datetime()))
        report = self.run_data()
        self.assertEqual((report["reactivated"], report["noop"], report["updated"]), (1, 2, 0))
        row = self.row()
        self.assertTrue(row["source_active"])
        self.assertFalse(row["source_deleted"])
        self.assertIsNone(row["source_deleted_at"])

    def test_reactivation_with_content_update(self):
        self.run_data()
        with self.repository.engine.begin() as connection:
            connection.execute(update(self.repository.programs).where(self.repository.programs.c.pblanc_id == self.base[0]["pblancId"])
                .values(source_active=False, source_deleted=True, source_deleted_at=utc_datetime()))
        changed = copy.deepcopy(self.base)
        changed[0]["pblancNm"] = "복원과 변경"
        report = self.run_data(self.data(changed))
        self.assertEqual((report["reactivated"], report["updated"]), (1, 1))

    def test_sample_unseen_no_delete(self):
        self.run_data()
        before = dict(self.row(self.base[1]["pblancId"]))
        report = self.run_data(self.data(self.base[:1]))
        self.assertEqual(report["soft_deleted"], 0)
        self.assertFalse(report["reconciliation_executed"])
        self.assertEqual(dict(self.row(self.base[1]["pblancId"])), before)

    def test_partial_unseen_no_delete(self):
        self.run_data()
        before = dict(self.row(self.base[1]["pblancId"]))
        report = self.run_data(self.data(self.base[:1], SyncScope.PARTIAL))
        self.assertEqual(report["soft_deleted"], 0)
        self.assertEqual(dict(self.row(self.base[1]["pblancId"])), before)

    def test_successful_full_soft_delete_and_no_physical_delete(self):
        self.run_data()
        before = self.count()
        # FULL fixture는 기존 test 행도 포함해 다른 테스트의 관측 이력을 보존한다.
        with self.repository.engine.connect() as connection:
            rows = connection.execute(select(self.repository.programs.c.source_payload).where(
                self.repository.programs.c.source_active.is_(True), self.repository.programs.c.pblanc_id != self.base[1]["pblancId"])).scalars().all()
        statements = []
        def capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)
        event.listen(self.repository.engine, "before_cursor_execute", capture)
        try:
            report = self.run_data(self.data(rows, SyncScope.FULL))
        finally:
            event.remove(self.repository.engine, "before_cursor_execute", capture)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["soft_deleted"], 1)
        self.assertTrue(report["reconciliation_executed"])
        unseen = self.row(self.base[1]["pblancId"])
        self.assertFalse(unseen["source_active"])
        self.assertTrue(unseen["source_deleted"])
        self.assertIsNotNone(unseen["source_deleted_at"])
        self.assertEqual(self.count(), before)
        self.assertFalse(any(s.lstrip().upper().startswith("DELETE ") for s in statements))

    def test_failed_page_full_skip(self):
        self.run_data()
        before = dict(self.row(self.base[1]["pblancId"]))
        data = SourceBatch(SyncScope.FULL, (SourcePage(1, 1, tuple(self.base[:1]), 2),
            SourcePage(2, 1, (), None, "TRANSPORT_ERROR")), "synthetic failed full", False)
        report = self.run_data(data)
        self.assertEqual(report["status"], "FAIL")
        self.assertFalse(report["reconciliation_executed"])
        self.assertIn("transport_errors", report["reconciliation_skipped_reason"])
        self.assertEqual(dict(self.row(self.base[1]["pblancId"])), before)

    def test_full_total_mismatch_skip(self):
        self.run_data()
        before = dict(self.row(self.base[1]["pblancId"]))
        report = self.run_data(self.data(self.base[:1], SyncScope.FULL, 2))
        self.assertFalse(report["reconciliation_executed"])
        self.assertIn("unique_count_totalCount_mismatch", report["reconciliation_skipped_reason"])
        self.assertEqual(dict(self.row(self.base[1]["pblancId"])), before)

    def test_full_inconsistent_totals_skip(self):
        self.run_data()
        data = SourceBatch(SyncScope.FULL, (SourcePage(1, 1, tuple(self.base[:1]), 2),
            SourcePage(2, 1, tuple(self.base[1:]), 3)), "synthetic", True)
        report = self.run_data(data)
        self.assertIn("totalCount_not_consistent", report["reconciliation_skipped_reason"])
        self.assertEqual(report["soft_deleted"], 0)

    def test_full_without_normal_termination_skip(self):
        self.run_data()
        data = replace(self.data(scope=SyncScope.FULL), pagination_terminated=False)
        report = self.run_data(data)
        self.assertIn("pagination_not_normally_terminated", report["reconciliation_skipped_reason"])
        self.assertFalse(report["reconciliation_executed"])

    def test_full_persistence_failure_rolls_back_presence(self):
        self.run_data()
        before = dict(self.row(self.base[1]["pblancId"]))
        with patch.object(self.repository, "verify", side_effect=RuntimeError("synthetic-db-secret")):
            report = self.run_data(self.data(self.base[:1], SyncScope.FULL))
        self.assertEqual(report["persistence_fatal_errors"], 1)
        self.assertEqual(report["soft_deleted"], 0)
        self.assertFalse(report["reconciliation_executed"])
        self.assertEqual(dict(self.row(self.base[1]["pblancId"])), before)

    def test_full_normalization_failure_skip(self):
        self.run_data()
        report = self.run_data(self.data([{"pblancId": " "}], SyncScope.FULL))
        self.assertIn("normalization_fatal_errors", report["reconciliation_skipped_reason"])
        self.assertFalse(report["reconciliation_executed"])

    def test_lifecycle_columns_never_change_fingerprint(self):
        self.run_data()
        before = self.row()
        second = self.run_data()
        after = self.row()
        self.assertEqual(before["source_fingerprint"], after["source_fingerprint"])
        self.assertNotEqual(before["last_seen_run_id"], after["last_seen_run_id"])
        self.assertEqual(second["noop"], 2)

    def test_full_duplicate_skip(self):
        self.run_data()
        before = dict(self.row())
        report = self.run_data(self.data([self.base[0], self.base[0]], SyncScope.FULL))
        self.assertEqual(report["duplicate_count"], 1)
        self.assertFalse(report["reconciliation_executed"])
        self.assertEqual(dict(self.row()), before)

    def test_full_api_contract_error_skip(self):
        self.run_data()
        for outcome in ("API_ERROR", "CONTRACT_ERROR"):
            data = SourceBatch(SyncScope.FULL, (SourcePage(1, 1, (), None, outcome),), "synthetic", False)
            report = self.run_data(data)
            self.assertFalse(report["reconciliation_executed"])
            self.assertEqual(report["soft_deleted"], 0)

    def test_normalization_failure_no_partial_write(self):
        data = self.data([self.base[0], {"pblancId": " "}])
        report = self.run_data(data)
        self.assertEqual(report["required_field_failures"], 1)
        self.assertEqual(report["inserted"], 0)
        self.assertIsNone(self.row())

    def test_transaction_rollback(self):
        original = self.repository.upsert
        calls = []
        def fail_second(connection, record, run_id):
            calls.append(record)
            if len(calls) == 2:
                raise RuntimeError("synthetic-secret-never-log")
            return original(connection, record, run_id)
        with patch.object(self.repository, "upsert", side_effect=fail_second):
            report = self.run_data()
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["inserted"], 0)
        self.assertEqual(report["persistence_fatal_errors"], 1)
        self.assertIsNone(self.row())
        self.assertNotIn("synthetic-secret", json.dumps(report))
        with self.repository.engine.connect() as connection:
            row = connection.execute(select(self.repository.runs).where(self.repository.runs.c.run_id == report["run_id"])).mappings().one()
        self.assertEqual(row["status"], "FAILED")
        self.assertEqual(row["report_json"]["inserted"], 0)

    def test_run_id_reuse_rejected(self):
        identifier = "test-" + uuid.uuid4().hex
        ingest(self.repository, self.data(), identifier)
        with self.assertRaises(PipelineError):
            ingest(self.repository, self.data(), identifier)

    def test_database_lock_blocks_concurrent_run(self):
        with self.repository.engine.connect() as connection:
            self.assertEqual(connection.execute(text("SELECT GET_LOCK(:name, 0)"), {"name": "biz-aid-sync:biz_aid_test"}).scalar(), 1)
            try:
                with self.assertRaises(PipelineError):
                    self.run_data()
            finally:
                connection.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": "biz-aid-sync:biz_aid_test"})

    def test_schema_presence_check(self):
        self.run_data()
        with self.assertRaises(DBAPIError), self.repository.engine.begin() as connection:
            connection.execute(update(self.repository.programs).where(self.repository.programs.c.pblanc_id == self.base[0]["pblancId"])
                .values(source_active=True, source_deleted=True))

    def test_null_blank_unknown_roundtrip(self):
        raw = dict(self.base[0], fileNm="", flpthNm=None, future={"nested": [None, ""]})
        report = self.run_data(self.data([raw]))
        self.assertEqual(report["status"], "PASS")
        row = self.row()
        self.assertEqual(row["source_payload"], raw)
        self.assertEqual(row["attachment_names_raw"], "")
        self.assertIsNone(row["attachment_urls_raw"])

    def test_synthetic_100_ingestion_and_gate(self):
        # CI에는 Live payload가 없어 합성 100건만 사용한다. 실제 동일 표본 Pilot은 CLI로 별도 실행한다.
        items = []
        for number in range(100):
            raw = copy.deepcopy(self.fixture[number % len(self.fixture)])
            raw["pblancId"] = self.prefix + "_" + str(number)
            items.append(raw)
        pages = tuple(SourcePage(n + 1, 20, tuple(items[n * 20:(n + 1) * 20]), 1514) for n in range(5))
        data = SourceBatch(SyncScope.SAMPLE, pages, "synthetic 5x20", False)
        first, second = self.run_data(data), self.run_data(data)
        self.assertEqual((first["input_count"], first["unique_pblanc_id_count"], first["inserted"], first["failed"]), (100, 100, 100, 0))
        self.assertEqual((second["inserted"], second["updated"], second["noop"], second["soft_deleted"]), (0, 0, 100, 0))
        self.assertEqual((first["date_parse_success"], first["date_free_text"]), (80, 20))
        self.assertEqual(first["invalid_url_count"], 0)


class DatabaseCommentMysqlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repository = MysqlRepository(replace(DbConfig.load(ROOT, "dev"), database="biz_aid_test"))

    @classmethod
    def tearDownClass(cls):
        cls.repository.close()

    def test_all_application_tables_and_columns_have_comments(self):
        for database in ("biz_aid_dev", "biz_aid_test"):
            repository = MysqlRepository(replace(DbConfig.load(ROOT, "dev"), database=database))
            try:
                with repository.engine.connect() as connection:
                    result = database_comments(connection)
                self.assertGreater(result["table_count"], 0)
                self.assertGreater(result["column_count"], 0)
                self.assertEqual(result["failures"], [])
            finally:
                repository.close()

    def check_fixture(self, definition):
        name = "comment_policy_" + uuid.uuid4().hex
        # 테스트 전용 DB의 빈 합성 테이블만 만들고 finally에서 제거한다. Pilot 테이블이나 기존 행은 건드리지 않는다.
        with self.repository.engine.begin() as connection:
            connection.exec_driver_sql(f"CREATE TABLE `{name}` {definition}")
            try:
                result = database_comments(connection)
                return name, result["failures"]
            finally:
                connection.exec_driver_sql(f"DROP TABLE `{name}`")

    def test_new_table_without_comment_fails(self):
        name, failures = self.check_fixture("(id INT COMMENT '회귀 검증용 합성 행 식별자')")
        self.assertIn({"object": name, "reason": "missing"}, failures)

    def test_new_column_without_comment_fails(self):
        name, failures = self.check_fixture("(id INT COMMENT '회귀 검증용 합성 행 식별자', added INT) COMMENT='신규 컬럼 정책 회귀를 위한 빈 합성 테이블'")
        self.assertIn({"object": name + ".added", "reason": "missing"}, failures)

    def test_placeholder_comment_fails(self):
        name, failures = self.check_fixture("(id INT COMMENT '값') COMMENT='TODO'")
        self.assertIn({"object": name, "reason": "placeholder_or_name_only"}, failures)
        self.assertIn({"object": name + ".id", "reason": "placeholder_or_name_only"}, failures)

    def test_new_commented_table_is_automatically_included(self):
        name, failures = self.check_fixture("(id INT COMMENT '회귀 검증용 합성 행 식별자') COMMENT='신규 테이블 자동 탐색을 검증하는 빈 합성 자료'")
        self.assertFalse(any(item["object"].startswith(name) for item in failures))
        self.assertEqual(failures, [])

    def test_v2_changes_only_comments_from_v1(self):
        prefix = "cm_" + uuid.uuid4().hex[:16]
        names = {"support_program_sync_history": prefix + "_runs", "support_programs": prefix + "_programs"}
        def statements(filename):
            sql = (ROOT / "migrations" / filename).read_text()
            for original, fixture in names.items():
                sql = sql.replace(original, fixture)
            return [item.strip() for item in sql.split(";") if item.strip()]
        def definition(connection, name):
            ddl = connection.exec_driver_sql(f"SHOW CREATE TABLE `{name}`").one()[1]
            ddl = re.sub(r" COMMENT(?:\s*=\s*|\s+)'(?:''|\\.|[^'\\])*'", "", ddl)
            columns = connection.execute(text("SELECT * FROM information_schema.columns WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=:name ORDER BY ORDINAL_POSITION"),
                {"name": name}).mappings().all()
            return ddl, [{k: v for k, v in row.items() if k != "COLUMN_COMMENT"} for row in columns]
        # 새 빈 fixture에 V1→V2를 적용해 현재 DB뿐 아니라 CI에서도 타입·키·제약 보존을 재현한다.
        with self.repository.engine.begin() as connection:
            created = []
            try:
                for statement, name in zip(statements("V1__structured_support_programs.sql"), names.values(), strict=True):
                    connection.exec_driver_sql(statement)
                    created.append(name)
                before = {name: definition(connection, name) for name in names.values()}
                for statement in statements("V2__add_database_comments.sql"):
                    connection.exec_driver_sql(statement)
                self.assertEqual({name: definition(connection, name) for name in names.values()}, before)
                result = database_comments(connection)
                self.assertFalse(any(item["object"].startswith(prefix) for item in result["failures"]))
            finally:
                for name in reversed(created):
                    connection.exec_driver_sql(f"DROP TABLE `{name}`")
