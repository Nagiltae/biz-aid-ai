"""HWP → PDF 변환 경계. 전용 Docker 이미지(LibreOffice headless + H2Orestart)만 쓰고 결과 PDF byte를 돌려준다.

변환된 PDF는 production PDF route(parse_pdf)가 그대로 읽는다. 이 모듈은 문서 구조를 해석하지 않으며 PDF를 저장하지 않는다.
"""
import json
import os
import shutil
import subprocess
import tempfile
import uuid
from functools import lru_cache
from pathlib import Path


class HwpConversionError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def image_ref(contract):
    spec = contract["routes"]["HWP"]["converter"]
    return f"{spec['image']}:{spec['dockerfile_sha256'][:12]}"


def _docker(*args, timeout):
    return subprocess.run(["docker", *args], capture_output=True, timeout=timeout, check=False)


@lru_cache(maxsize=2)
def _identity(ref, dockerfile_sha256, label, timeout):
    if shutil.which("docker") is None:
        raise HwpConversionError("hwp_converter_unavailable")
    try:
        inspected = _docker("image", "inspect", "--format", "{{json .Config.Labels}}", ref, timeout=timeout)
        if inspected.returncode != 0:
            raise HwpConversionError("hwp_converter_unavailable")
        # RISK: 같은 tag라도 다른 Dockerfile로 만든 이미지면 변환 결과가 달라지므로 build label로 identity를 확인한다.
        if (json.loads(inspected.stdout or b"null") or {}).get(label) != dockerfile_sha256:
            raise HwpConversionError("hwp_converter_identity_mismatch")
        versions = _docker("run", "--rm", "--network", "none", "--entrypoint", "cat", ref,
                           "/opt/bizaid/libreoffice-version", "/opt/bizaid/h2orestart-version", timeout=timeout)
    except subprocess.TimeoutExpired:
        raise HwpConversionError("hwp_converter_unavailable") from None
    if versions.returncode != 0:
        raise HwpConversionError("hwp_converter_unavailable")
    libreoffice, h2orestart = versions.stdout.decode().strip().splitlines()[:2]
    # 실제 LibreOffice·H2Orestart 버전과 Dockerfile hash를 parse_key의 converter_version으로 쓴다.
    return f"{libreoffice.strip()} | H2Orestart {h2orestart.split()[0]} | dockerfile {dockerfile_sha256[:12]}"


def converter_version(contract):
    spec = contract["routes"]["HWP"]["converter"]
    return _identity(image_ref(contract), spec["dockerfile_sha256"], spec["image_label"], spec["run"]["timeout_seconds"])


def convert_hwp(raw, contract):
    """HWP byte를 PDF byte로 바꾼다. 임시 디렉터리는 성공·실패와 관계없이 지운다."""
    run = contract["routes"]["HWP"]["converter"]["run"]
    name = f"bizaid-hwp-{uuid.uuid4().hex[:12]}"
    # BOUNDARY: 로컬 디스크는 변환 중 임시 작업 공간일 뿐 문서 저장소가 아니다.
    with tempfile.TemporaryDirectory(prefix="bizaid-hwp-") as work:
        root = Path(work)
        (root / "in").mkdir()
        (root / "out").mkdir()
        (root / "in/source.hwp").write_bytes(raw)
        user = run["user"] if run["user"] != "caller" else _caller()
        command = ["run", "--rm", "--name", name, "--network", run["network"], "--user", user,
                   "--tmpfs", "/tmp", "-v", f"{root}:/work", image_ref(contract), "/work/in/source.hwp"]
        try:
            completed = _docker(*command, timeout=run["timeout_seconds"])
        except subprocess.TimeoutExpired:
            # RISK: docker CLI만 끝나고 container가 남지 않도록 이름으로 강제 종료한다.
            _docker("rm", "-f", name, timeout=60)
            raise HwpConversionError("hwp_conversion_timeout") from None
        if completed.returncode != 0:
            raise HwpConversionError("hwp_conversion_failed")
        output = root / "out/source.pdf"
        # EXCEPTION: LibreOffice는 import filter가 실패해도 종료 코드 0을 낼 수 있어 산출물로만 성공을 판정한다.
        if not output.is_file() or not output.read_bytes()[:5] == b"%PDF-":
            raise HwpConversionError("hwp_conversion_no_output")
        return output.read_bytes()


def _caller():
    return f"{os.getuid()}:{os.getgid()}"
