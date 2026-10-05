"""릴리스는 가짜 Git·Docker로만 검사한다. 실제 빌드·push·인증 파일·사용자 설정에는 접근하지 않는다."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
REVISION = "a" * 40

FAKE_DOCKER = '''import json,os,sys
from pathlib import Path
a=sys.argv[1:]
with Path(os.environ['CALLS']).open('a') as out: out.write(json.dumps(a)+'\\n')
mode=os.environ.get('FAKE_MODE','absent')
if a==['info']: sys.exit(1 if mode=='daemon_down' else 0)
if a[:2]==['buildx','version']: sys.exit(1 if mode=='no_buildx' else 0)
if a[:3]==['buildx','imagetools','inspect']:
    ref=a[3]
    if ref.endswith(':backend-20261005-03'):
        if mode=='logged_out': print('unauthorized fixture-secret',file=sys.stderr); sys.exit(1)
        sys.exit(0)
    state=Path(os.environ['COUNTERS'])
    counts=json.loads(state.read_text()) if state.exists() else {}
    counts[ref]=counts.get(ref,0)+1
    state.write_text(json.dumps(counts))
    if mode=='exists' or (mode=='second_exists' and ':fastapi-' in ref) or (mode=='appeared' and counts[ref]>=2): sys.exit(0)
    if mode=='registry_error': print('HTTP 503 fixture-secret',file=sys.stderr); sys.exit(1)
    if mode=='denied_target': print('unauthorized: not found fixture-secret',file=sys.stderr); sys.exit(1)
    print('ERROR: docker.io/'+ref+': not found',file=sys.stderr)
    sys.exit(1)
if a[:2]==['buildx','build']:
    if mode=='changed_source': Path(os.environ['CHANGED']).touch()
    if mode=='build_failed': print('fixture-secret',file=sys.stderr); sys.exit(1)
    sys.exit(0)
if a[:2]==['image','inspect']:
    if 'Architecture' in a[3]: print(os.environ.get('FAKE_PLATFORM','linux/amd64'))
    elif 'org.bizaid.release-tag' in a[3]: print(os.environ.get('FAKE_RELEASE_TAG',a[-1].rsplit(':',1)[-1].split('-',1)[1]))
    else: print(os.environ.get('FAKE_LABEL','a'*40))
    sys.exit(0)
if a[0]=='tag': sys.exit(0)
if a[0]=='push':
    if mode=='push_failed': print('fixture-secret',file=sys.stderr); sys.exit(1)
    if mode=='latest_failed' and a[1].endswith('-latest'): print('fixture-secret',file=sys.stderr); sys.exit(1)
    sys.exit(0)
sys.exit(2)
'''
FAKE_GIT = '''import os,sys
from pathlib import Path
a=sys.argv[1:]
if a[:1]==['-C']: a=a[2:]
if a[0]=='status':
    if os.environ.get('FAKE_DIRTY')=='1' or Path(os.environ['CHANGED']).exists(): print(' M source.py')
elif a[0]=='rev-parse': print('a'*40)
else: sys.exit(2)
'''


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.work = self.directory / "work tree"
        (self.work / "scripts").mkdir(parents=True)
        self.script = self.work / "scripts/release.sh"
        shutil.copy2(ROOT / "scripts/release.sh", self.script)
        self.bin = self.directory / "bin"
        self.bin.mkdir()
        for name, body in (("docker", FAKE_DOCKER), ("git", FAKE_GIT)):
            path = self.bin / name
            path.write_text("#!" + sys.executable + "\n" + body)
            path.chmod(0o755)
        self.calls = self.directory / "calls"
        self.environment = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ["PATH"],
            BIZAID_IMAGE_REPO="fixture/deploy", BIZAID_BACKEND_TAG="20261005-03", CALLS=str(self.calls),
            COUNTERS=str(self.directory / "counters"), CHANGED=str(self.directory / "changed"))

    def run_release(self, *args, **changes):
        return subprocess.run([str(self.script), *args], env=dict(self.environment, **changes), capture_output=True, text=True)

    def docker_calls(self):
        return [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []

    def test_argument_errors_stop_before_docker(self):
        for args in ((), ("new",), ("new;command", "backend"), ("new", "mysql"),
                     ("new", "backend", "backend"), ("new", "backend", "--unknown"), ("--dry-run",), ("latest", "backend")):
            with self.subTest(args=args):
                self.assertEqual(self.run_release(*args).returncode, 2)
        self.assertEqual(self.docker_calls(), [])

    def test_dry_run_prints_selected_builds_label_and_server_steps_without_docker(self):
        result = self.run_release("new", "backend", "fastapi", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("DRY-RUN", result.stdout)
        self.assertIn("--platform linux/amd64 --load", result.stdout)
        self.assertIn("org.opencontainers.image.revision=" + REVISION, result.stdout)
        self.assertIn("org.bizaid.release-tag=new", result.stdout)
        self.assertIn("docker tag fixture/deploy:backend-new fixture/deploy:backend-latest", result.stdout)
        self.assertIn("docker push fixture/deploy:fastapi-latest", result.stdout)
        self.assertIn("bash scripts/deploy.sh backend fastapi", result.stdout)
        self.assertEqual(self.docker_calls(), [])

    def test_dirty_tree_blocks_real_and_dry_run_before_docker(self):
        for options in ((), ("--dry-run",)):
            result = self.run_release("new", "backend", *options, FAKE_DIRTY="1")
            self.assertEqual(result.returncode, 1)
            self.assertIn("커밋하지 않은 변경", result.stderr)
        self.assertEqual(self.docker_calls(), [])

    def test_existing_tag_blocks_all_builds_and_pushes(self):
        for mode in ("exists", "second_exists"):
            result = self.run_release("new", "backend", "fastapi", FAKE_MODE=mode)
            self.assertEqual(result.returncode, 1)
            self.assertIn("덮어쓰지", result.stderr)
        self.assertFalse(any(call[:2] == ["buildx", "build"] or call[0] == "push" for call in self.docker_calls()))

    def test_login_buildx_daemon_and_registry_errors_block_build(self):
        for mode, reason in [("logged_out", "docker login"), ("no_buildx", "buildx"), ("daemon_down", "Docker Desktop"),
                             ("registry_error", "태그 부재"), ("denied_target", "태그 조회")]:
            result = self.run_release("new", "backend", FAKE_MODE=mode)
            self.assertEqual(result.returncode, 1)
            self.assertIn(reason, result.stderr)
            self.assertNotIn("fixture-secret", result.stderr + result.stdout)
        self.assertFalse(any(call[:2] == ["buildx", "build"] or call[0] == "push" for call in self.docker_calls()))

    def test_missing_docker_explains_requirement(self):
        (self.bin / "docker").unlink()
        for command in ("bash", "dirname"):
            (self.bin / command).symlink_to(shutil.which(command))
        result = self.run_release("new", "backend", PATH=str(self.bin))
        self.assertEqual(result.returncode, 1)
        self.assertIn("Docker가 없습니다", result.stderr)
        self.assertEqual(self.docker_calls(), [])

    def test_backend_only_uses_original_root_context(self):
        result = self.run_release("new", "backend")
        self.assertEqual(result.returncode, 0, result.stderr)
        builds = [call for call in self.docker_calls() if call[:2] == ["buildx", "build"]]
        self.assertEqual(len(builds), 1)
        self.assertEqual(Path(builds[0][builds[0].index("-f") + 1]).resolve(), (self.work / "backend/Dockerfile").resolve())
        self.assertEqual(Path(builds[0][-1]).resolve(), self.work.resolve())
        self.assertEqual([call[1] for call in self.docker_calls() if call[0] == "push"], ["fixture/deploy:backend-new", "fixture/deploy:backend-latest"])
        self.assertNotIn("BIZAID_FRONTEND_TAG=new", result.stdout)
        self.assertNotIn("BIZAID_FASTAPI_TAG=new", result.stdout)

    def test_selected_services_use_original_build_contexts_and_committed_revision(self):
        result = self.run_release("new", "frontend", "fastapi")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.docker_calls()
        builds = [call for call in calls if call[:2] == ["buildx", "build"]]
        self.assertEqual(len(builds), 2)
        expected = [(self.work / "frontend/Dockerfile.prod", self.work / "frontend", "frontend"),
                    (self.work / "data-pipeline/Dockerfile.prod", self.work, "fastapi")]
        for args, (dockerfile, context, service) in zip(builds, expected):
            self.assertEqual(args[args.index("--platform") + 1], "linux/amd64")
            self.assertIn("--load", args)
            self.assertEqual(Path(args[args.index("-f") + 1]).resolve(), dockerfile.resolve())
            self.assertEqual(Path(args[-1]).resolve(), context.resolve())
            self.assertEqual(args[args.index("-t") + 1], "fixture/deploy:" + service + "-new")
            self.assertIn("org.opencontainers.image.revision=" + REVISION, args)
        self.assertEqual([call[1] for call in calls if call[0] == "push"], ["fixture/deploy:frontend-new", "fixture/deploy:fastapi-new", "fixture/deploy:frontend-latest", "fixture/deploy:fastapi-latest"])
        self.assertNotIn("BIZAID_BACKEND_TAG=new", result.stdout)

    def test_tag_appearing_during_build_blocks_push(self):
        result = self.run_release("new", "backend", FAKE_MODE="appeared")
        self.assertEqual(result.returncode, 1)
        self.assertTrue(any(call[:2] == ["buildx", "build"] for call in self.docker_calls()))
        self.assertFalse(any(call[0] == "push" for call in self.docker_calls()))

    def test_changed_source_and_wrong_image_metadata_block_push(self):
        for environment in ({"FAKE_MODE": "changed_source"}, {"FAKE_PLATFORM": "linux/arm64"}, {"FAKE_LABEL": "b" * 40}, {"FAKE_RELEASE_TAG": "wrong"}):
            result = self.run_release("new", "backend", **environment)
            self.assertEqual(result.returncode, 1)
            (self.directory / "changed").unlink(missing_ok=True)
        self.assertFalse(any(call[0] == "push" for call in self.docker_calls()))

    def test_build_and_push_failure_hide_raw_output_and_do_not_offer_server_apply(self):
        for mode in ("build_failed", "push_failed", "latest_failed"):
            result = self.run_release("new", "backend", FAKE_MODE=mode)
            self.assertEqual(result.returncode, 1)
            self.assertNotIn("fixture-secret", result.stdout + result.stderr)
            self.assertNotIn("bash scripts/deploy.sh", result.stdout)

    def test_auto_tag_uses_korean_time_and_latest_is_not_probed(self):
        date = self.bin / "date"
        date.write_text('#!/bin/sh\n[ "$TZ" = Asia/Seoul ] || exit 1\n[ "$1" = +%Y%m%d-%H%M ] || exit 1\nprintf "20261006-0115\\n"\n')
        date.chmod(0o755)
        result = self.run_release("backend")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.docker_calls()
        self.assertIn(["tag", "fixture/deploy:backend-20261006-0115", "fixture/deploy:backend-latest"], calls)
        self.assertFalse(any(c[:3] == ["buildx", "imagetools", "inspect"] and c[-1].endswith('-latest') for c in calls))
        self.assertIn("bash scripts/deploy.sh backend", result.stdout)
        self.assertTrue(all("org.bizaid.release-tag=20261006-0115" in c for c in calls if c[:2] == ["buildx", "build"]))


if __name__ == "__main__":
    unittest.main()
