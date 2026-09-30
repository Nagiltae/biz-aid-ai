import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESOURCES = ROOT / "backend/src/main/resources"


class SpringProfileTests(unittest.TestCase):
    """Spring dev/prod 설정 분리 규칙: 비밀값은 어떤 profile에도 없고, prod는 로컬 기본값 없이 환경변수로만 받는다."""

    def test_prod_profile_requires_environment_and_secure_cookie(self):
        prod = (RESOURCES / "application-prod.yml").read_text(encoding="utf-8")
        # BOUNDARY: 운영 주소는 기본값을 두지 않는다(로컬 127.0.0.1·host.docker.internal이 운영에 조용히 섞이지 않게).
        for name in ("MYSQL_HOST", "MYSQL_PORT", "MYSQL_DATABASE", "AI_BASE_URL", "FLYWAY_LOCATIONS"):
            self.assertIn("${" + name + "}", prod)
        settings = "\n".join(line for line in prod.splitlines() if not line.lstrip().startswith("#"))
        self.assertNotRegex(settings, r"127\.0\.0\.1|localhost|host\.docker\.internal")
        self.assertRegex(prod, r"refresh-cookie:\n(?:\s+#.*\n)*\s+secure: true\n")
        self.assertIn("sslMode=", prod)

    def test_no_profile_contains_secret_values(self):
        for path in RESOURCES.glob("application*.yml"):
            text = path.read_text(encoding="utf-8")
            with self.subTest(profile=path.name):
                self.assertIn(path.name, {"application.yml", "application-dev.yml", "application-prod.yml"})
                # 비밀값은 환경변수 참조로만 쓴다(기본값으로 실제 값을 넣지 않는다).
                for key in ("password", "secret", "api-key"):
                    for value in re.findall(rf"^\s*{key}:\s*(.+)$", text, re.MULTILINE):
                        self.assertRegex(value.strip(), r"^\$\{[A-Z_]+:?\}$", f"{path.name} {key}")


if __name__ == "__main__":
    unittest.main()
