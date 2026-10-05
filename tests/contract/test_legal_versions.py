"""묶음5-1: 약관·개인정보처리방침 버전과 공개 서비스 설정의 서버·화면 일치 검사(실행 서버 없이 파일만 읽는다)."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND_YML = ROOT / "backend/src/main/resources/application.yml"
FRONTEND_VERSIONS = ROOT / "frontend/src/features/legal/legalVersions.ts"
MIGRATION = ROOT / "migrations/V13__public_service_trial_usage_consent.sql"


class LegalVersionTests(unittest.TestCase):
    def test_backend_and_screen_show_the_same_document_versions(self):
        # BOUNDARY: 동의 기록(user_consents)에는 서버 버전이 남는다. 화면이 다른 버전을 보여 주면 기록이 틀린다.
        yml = BACKEND_YML.read_text(encoding="utf-8")
        screen = FRONTEND_VERSIONS.read_text(encoding="utf-8")
        for server_key, screen_name in (("terms-version", "TERMS_VERSION"), ("privacy-version", "PRIVACY_VERSION")):
            server = re.search(rf'^\s+{server_key}: "([^"]+)"', yml, re.MULTILINE).group(1)
            shown = re.search(rf'export const {screen_name} = "([^"]+)";', screen).group(1)
            self.assertEqual(server, shown, server_key)
            # 버전은 V13 column 길이(20)·시행일 형식을 따른다.
            self.assertRegex(server, r"^\d{4}-\d{2}-\d{2}(?:\.\d+)?$")

    def test_public_service_defaults(self):
        yml = BACKEND_YML.read_text(encoding="utf-8")
        # 사용자 결정 값: 계정10/IP30회, 체험 합산 200회, 24시간 수명. 체험하기는 기본 끔(dev profile만 켬).
        self.assertIn("daily-limit: ${BIZAID_AI_DAILY_LIMIT:10}", yml)
        self.assertIn("daily-limit-per-ip: ${BIZAID_AI_DAILY_LIMIT_PER_IP:30}", yml)
        self.assertIn("daily-pool-limit: ${BIZAID_TRIAL_DAILY_POOL_LIMIT:200}", yml)
        self.assertIn("enabled: ${BIZAID_TRIAL_ENABLED:false}", yml)
        self.assertRegex(yml, r"\n      ttl: 24h\n")
        prod = (ROOT / "backend/src/main/resources/application-prod.yml").read_text(encoding="utf-8")
        self.assertNotIn("BIZAID_TRIAL_ENABLED:true", prod)

    def test_v13_comments_every_column(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        for table in ("user_consents", "ai_usage_counters"):
            body = re.search(rf"CREATE TABLE {table} \((.*?)\n\) ENGINE", sql, re.DOTALL).group(1)
            columns = re.findall(r"^    ([a-z_]+) [A-Z]", body, re.MULTILINE)
            self.assertTrue(columns)
            for column in columns:
                self.assertRegex(body, rf"\n    {column} [^\n]* COMMENT '[^']+'", column)
        self.assertIn("account_type VARCHAR(10)", sql)
        # 이메일·IP 원문은 사용 횟수 key에 넣지 않는다.
        self.assertIn("TRIAL_IP:<SHA-256>", sql)


if __name__ == "__main__":
    unittest.main()
