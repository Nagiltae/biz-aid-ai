import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote, unquote

ROOT = Path(__file__).resolve().parents[4]
S3_REGION = "ap-southeast-2"
S3_BUCKET = "amazon-s3-biz-aid-bucket-695694684371-ap-southeast-2-an"
S3_PREFIX = "biz-aid/documents"


class PipelineError(ValueError):
    pass


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise PipelineError("duplicate_json_key")
            result[key] = value
        return result
    def constant(value):
        raise PipelineError("invalid_json_constant")
    return json.loads(Path(path).read_bytes(), object_pairs_hook=unique, parse_constant=constant)


def api_contract(root=ROOT):
    return read_json(root / "contracts/external-api/bizinfo.contract.json")


def values(path, names, environ):
    result = {}
    # 사용자 설정은 KEY=VALUE로만 읽는다. 셸 보간과 다른 Profile로의 대체는 환경 경계를 깨뜨린다.
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            name, separator, value = line.strip().removeprefix("export ").partition("=")
            name, value = name.strip(), value.strip()
            if separator and name in names:
                if value.startswith(("'", '"')):
                    if len(value) < 2 or value[-1] != value[0]:
                        raise PipelineError("invalid_env_format")
                    value = value[1:-1]
                result[name] = value
    result.update({key: environ[key] for key in names if key in environ})
    return result


def credential_echo(raw, key):
    if not key:
        return False
    text = raw.decode("utf-8", errors="replace")
    candidates = [text, unquote(text)]
    try:
        candidates.append(json.dumps(json.loads(raw), ensure_ascii=False))
    except (ValueError, UnicodeError, RecursionError):
        pass
    return any(key in item or quote(key, safe="") in item for item in candidates)


def profile_values(root, profile, names, environ=None):
    if profile not in ("dev", "prod"):
        raise PipelineError("unsupported_profile")
    return values(root / f".env.{profile}", names, os.environ if environ is None else environ)


@dataclass(frozen=True)
class ApiConfig:
    profile: str
    endpoint: str
    key: str = field(repr=False)

    @classmethod
    def load(cls, root, profile, environ=None):
        if profile not in ("dev", "prod"):
            raise PipelineError("unsupported_profile")
        spec = api_contract(root)
        config = profile_values(root, profile, {"BIZINFO_API_BASE_URL", "BIZINFO_SERVICE_KEY", "BIZINFO_DATA_TYPE"}, environ)
        endpoint = config.get("BIZINFO_API_BASE_URL", spec["request"]["endpoint"])
        if endpoint != spec["request"]["endpoint"] or config.get("BIZINFO_DATA_TYPE", "json") != "json":
            raise PipelineError("unsupported_api_configuration")
        key = unquote(config.get("BIZINFO_SERVICE_KEY", "").strip())
        if any(ord(c) < 32 for c in key):
            raise PipelineError("invalid_credential_format")
        return cls(profile, endpoint, key)


@dataclass(frozen=True)
class DbConfig:
    host: str
    port: int
    database: str
    user: str
    password: str = field(repr=False)
    profile: str = "dev"

    @classmethod
    def load(cls, root, profile, environ=None):
        if profile != "dev":
            raise PipelineError("prod_database_access_forbidden")
        names = {"MYSQL_HOST", "MYSQL_PORT", "MYSQL_DATABASE", "MYSQL_USER", "MYSQL_PASSWORD"}
        config = profile_values(root, profile, names, environ)
        missing = sorted(name for name in ("MYSQL_DATABASE", "MYSQL_USER", "MYSQL_PASSWORD") if not config.get(name))
        if missing:
            raise PipelineError("dev_database_configuration_required:" + ",".join(missing))
        try:
            result = cls(config.get("MYSQL_HOST", "127.0.0.1"), int(config.get("MYSQL_PORT", "3306")),
                         config["MYSQL_DATABASE"], config["MYSQL_USER"], config["MYSQL_PASSWORD"])
        except (KeyError, ValueError):
            raise PipelineError("dev_database_configuration_required") from None
        if (result.host not in ("127.0.0.1", "localhost", "mysql") or result.database not in ("biz_aid_dev", "biz_aid_test")
                or not result.password or result.port != 3306):
            raise PipelineError("dev_database_boundary")
        return result

@dataclass(frozen=True)
class S3Config:
    region: str
    bucket: str
    prefix: str
    profile: str = "dev"

    @classmethod
    def load(cls, root, profile, environ=None):
        # Phase 2.5의 실제 S3 작업은 dev 환경에서만 허용한다.
        if profile != "dev":
            raise PipelineError("prod_s3_access_forbidden")

        names = {
            "AWS_REGION",
            "AWS_S3_BUCKET",
            "AWS_S3_PREFIX",
        }

        config = profile_values(
            root,
            profile,
            names,
            environ,
        )

        missing = sorted(
            name
            for name in ("AWS_REGION", "AWS_S3_BUCKET")
            if not config.get(name, "").strip()
        )

        if missing:
            raise PipelineError(
                "dev_s3_configuration_required:"
                + ",".join(missing)
            )

        region = config["AWS_REGION"].strip()
        bucket = config["AWS_S3_BUCKET"].strip()
        prefix = config.get("AWS_S3_PREFIX", S3_PREFIX).strip("/")

        if not prefix:
            raise PipelineError(
                "dev_s3_configuration_required:AWS_S3_PREFIX"
            )

        # Phase 2.5 검증 대상은 사용자가 확정한 단일 dev 저장소다.
        # 잘못된 환경변수로 다른 버킷을 검증하거나 DB에 기록하지 못하게 한다.
        if (region, bucket, prefix) != (S3_REGION, S3_BUCKET, S3_PREFIX):
            raise PipelineError("unsupported_s3_configuration")

        return cls(
            region=region,
            bucket=bucket,
            prefix=prefix,
            profile=profile,
        )
