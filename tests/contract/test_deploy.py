"""임시 서버 폴더와 가짜 Docker/curl/smoke만 사용한다. 사용자 설정·운영 서버에는 접근하지 않는다."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
OLD = "20261005-03"
NEW = "20261006-0115"
SECRETS = 'MYSQL_PASSWORD=fixture-secret\nJWT_SECRET="fixture-jwt # literal"\nINTERNAL_AI_API_KEY=fixture-ai\n'
FAKE_DOCKER = '''import json,os,re,sys
from pathlib import Path
a=sys.argv[1:]
mode=os.environ.get('FAKE_MODE','')
with Path(os.environ['CALLS']).open('a') as f: f.write(json.dumps(a)+'\\n')
state_path=Path(os.environ['STATE'])
state=json.loads(state_path.read_text()) if state_path.exists() else {}
if a[0]=='pull':
    if mode=='latest_pull_failed': print('fixture-secret',file=sys.stderr); sys.exit(1)
    sys.exit(0)
if a[:2]==['image','inspect']:
    print('<no value>' if mode=='missing_label' else ('latest' if mode=='bad_label' else os.environ.get('LATEST_TAG','20261006-0115')))
    sys.exit(0)
if a[0]=='compose':
    assert os.environ.get('COMPOSE_DISABLE_ENV_FILE')=='1'
    assert all(n not in os.environ for n in ('BIZAID_IMAGE_REPO','BIZAID_FRONTEND_TAG','BIZAID_BACKEND_TAG','BIZAID_FASTAPI_TAG','CADDY_SITE','BIZAID_IMAGE_PLATFORM'))
    assert a[1]=='--env-file' and a[3]=='-f'
    args=a[5:]
    env=Path(a[2])
    values={}
    for line in env.read_text().splitlines():
        match=re.match(r'\\s*(?:export\\s+)?([A-Z_0-9]+)\\s*=\\s*(.*)',line)
        if match: values[match[1]]=match[2].split(' #',1)[0].strip().strip('"')
    if args[:2]==['config','--quiet']:
        if mode=='config_failed': print('fixture-secret',file=sys.stderr); sys.exit(1)
        sys.exit(0)
    if args[0]=='pull':
        if mode=='version_pull_failed': print('fixture-secret',file=sys.stderr); sys.exit(1)
        assert all(not values.get('BIZAID_'+s.upper()+'_TAG','').endswith('latest') for s in args[1:])
        sys.exit(0)
    if args[:3]==['exec','-T','fastapi']: sys.exit(0)
    if args[:3]==['up','-d','--no-deps']:
        if mode=='up_failed': print('fixture-secret',file=sys.stderr); sys.exit(1)
        for s in args[3:]: state[s]=values['BIZAID_IMAGE_REPO']+':'+s+'-'+values['BIZAID_'+s.upper()+'_TAG']
        state_path.write_text(json.dumps(state))
        sys.exit(0)
    if args[:1]==['ps']:
        if mode=='ps_failed': print('fixture-secret',file=sys.stderr); sys.exit(1)
        rows=[{'Service':s,'Image':image,'State':'exited' if mode=='not_running' else 'running','Health':''} for s,image in state.items()]
        if mode=='wrong_image':
            for row in rows:row['Image']='fixture/deploy:wrong-version'
        if mode=='ndjson':print('\\n'.join(json.dumps(r) for r in rows))
        else:print(json.dumps(rows))
        sys.exit(0)
sys.exit(2)
'''


class DeployTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "server folder"
        (self.root / "scripts").mkdir(parents=True)
        self.script = self.root / "scripts/deploy.sh"
        shutil.copy2(ROOT / "scripts/deploy.sh", self.script)
        (self.root / "docker-compose.prod.yml").write_text("name: biz-aid-prod\n")
        self.env_file = self.root / ".env.prod"
        self.original = ('# synthetic server settings\nBIZAID_IMAGE_REPO=fixture/deploy\n'
                         'BIZAID_FRONTEND_TAG=' + OLD + '\nBIZAID_BACKEND_TAG=' + OLD + '\n'
                         'BIZAID_FASTAPI_TAG=' + OLD + '\nCADDY_SITE=fixture.invalid\n' + SECRETS)
        self.env_file.write_text(self.original)
        self.env_file.chmod(0o600)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.calls = self.root / "calls.jsonl"
        self.state = self.root / "state.json"
        self.state.write_text(json.dumps({s: "fixture/deploy:" + s + "-" + OLD for s in ("frontend", "backend", "fastapi")}))
        for name, source in (("docker", FAKE_DOCKER), ("curl", "import sys\nsys.exit(0)\n")):
            path = self.bin / name
            path.write_text("#!" + sys.executable + "\n" + source)
            path.chmod(0o755)
        smoke = self.root / "scripts/smoke_prod.sh"
        smoke.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$1" >> "$SMOKE_CALLS"\n'
                         'if [[ ${FAKE_MODE:-} == smoke_failed ]]; then echo \'{"stage":"ai_query","http_status":500,"reason":"HTTPError","body_preview":"fixture-secret"}\' >&2; exit 1; fi\n'
                         'echo \'{"status":"PASS"}\'\n')
        self.smoke_calls = self.root / "smoke-calls"
        self.environment = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ["PATH"], CALLS=str(self.calls),
                                STATE=str(self.state), SMOKE_CALLS=str(self.smoke_calls), BIZAID_BACKEND_TAG="wrong-export",
                                CADDY_SITE="wrong-export", BIZAID_IMAGE_PLATFORM="linux/arm64")

    def run_deploy(self, *args, **environment):
        return subprocess.run(["bash", str(self.script), *args], env=dict(self.environment, **environment), capture_output=True, text=True)

    def docker_calls(self):
        return [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []

    def assert_no_secret_output(self, result):
        for secret in ("fixture-secret", "fixture-jwt", "fixture-ai"):
            self.assertNotIn(secret, result.stdout + result.stderr)

    def test_latest_uses_label_and_only_selected_line_with_private_backup(self):
        result = self.run_deploy("backend")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.env_file.read_text(), self.original.replace("BIZAID_BACKEND_TAG=" + OLD, "BIZAID_BACKEND_TAG=" + NEW))
        backups = list(self.root.glob('.env.prod.backup-*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), self.original)
        self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.env_file.stat().st_mode & 0o777, 0o600)
        record = (self.root / 'deploy-history.log').read_text().strip().split('\t')
        self.assertEqual(record[1:], ['backend', OLD, NEW])
        self.assertEqual((self.root / 'deploy-history.log').stat().st_mode & 0o777, 0o600)
        calls = self.docker_calls()
        self.assertIn(['pull', '--platform', 'linux/amd64', 'fixture/deploy:backend-latest'], calls)
        self.assertTrue(any(c[-4:] == ['up', '-d', '--no-deps', 'backend'] for c in calls))
        self.assertEqual(self.smoke_calls.read_text().strip(), 'https://fixture.invalid')
        self.assertIn('backend | ' + OLD + ' | ' + NEW, result.stdout)
        self.assertIn('bash scripts/deploy.sh backend=' + OLD, result.stdout)
        self.assert_no_secret_output(result)
        self.assertFalse((self.root / '.deploy.lock').exists())

    def test_explicit_old_image_needs_no_latest_or_labels(self):
        result = self.run_deploy('backend=20261004-01', FAKE_MODE='missing_label')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any(c[0] == 'pull' or c[:2] == ['image', 'inspect'] for c in self.docker_calls()))
        self.assertIn('BIZAID_BACKEND_TAG=20261004-01', self.env_file.read_text())

    def test_status_old_images_reads_only_tags_and_running_images(self):
        before = self.env_file.read_bytes()
        result = self.run_deploy('status', FAKE_MODE='ndjson')
        self.assertEqual(result.returncode, 0, result.stderr)
        for service in ('frontend', 'backend', 'fastapi'):
            self.assertIn(service + ' | ' + OLD + ' | fixture/deploy:' + service + '-' + OLD, result.stdout)
        self.assertEqual(self.env_file.read_bytes(), before)
        self.assertFalse((self.root / 'deploy-history.log').exists())
        self.assertEqual(len(self.docker_calls()), 1)
        self.assert_no_secret_output(result)

    def test_same_latest_skips_write_up_and_smoke(self):
        result = self.run_deploy('backend', LATEST_TAG=OLD)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('이미 최신', result.stdout)
        self.assertEqual(self.env_file.read_text(), self.original)
        self.assertFalse(list(self.root.glob('.env.prod.backup-*')))
        self.assertFalse((self.root / 'deploy-history.log').exists())
        self.assertFalse(self.smoke_calls.exists())
        self.assertFalse(any(c[0] == 'compose' for c in self.docker_calls()))

    def test_mixed_services_only_changed_subset_and_one_smoke(self):
        self.env_file.write_text(self.original.replace('BIZAID_FRONTEND_TAG=' + OLD, 'BIZAID_FRONTEND_TAG=' + NEW))
        result = self.run_deploy('frontend', 'backend')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(any(c[-4:] == ['up', '-d', '--no-deps', 'backend'] for c in self.docker_calls()))
        self.assertEqual(len(self.smoke_calls.read_text().splitlines()), 1)
        self.assertIn('BIZAID_FASTAPI_TAG=' + OLD, self.env_file.read_text())

    def test_fastapi_readiness_probe_precedes_single_smoke(self):
        result = self.run_deploy('fastapi')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(any(c[5:8] == ['exec', '-T', 'fastapi'] for c in self.docker_calls()))
        self.assertEqual(len(self.smoke_calls.read_text().splitlines()), 1)

    def test_failure_history_can_restore_previous_without_labels(self):
        failed = self.run_deploy('backend', FAKE_MODE='smoke_failed')
        self.assertEqual(failed.returncode, 1)
        recovered = self.run_deploy('--rollback', 'backend', FAKE_MODE='missing_label')
        self.assertEqual(recovered.returncode, 0, recovered.stderr)
        self.assertEqual(self.env_file.read_text(), self.original)

    def test_missing_selected_line_is_added_and_unrelated_bytes_preserved(self):
        missing = self.original.replace('BIZAID_BACKEND_TAG=' + OLD + '\n', '').rstrip('\n')
        self.env_file.write_text(missing)
        result = self.run_deploy('backend=' + NEW)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.env_file.read_text(), missing + '\nBIZAID_BACKEND_TAG=' + NEW + '\n')

    def test_recorded_previous_tags_rollback_all_selected_and_can_toggle(self):
        self.assertEqual(self.run_deploy('frontend', 'backend').returncode, 0)
        result = self.run_deploy('--rollback', 'frontend', 'backend')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.env_file.read_text(), self.original)
        records = (self.root / 'deploy-history.log').read_text().splitlines()
        self.assertEqual(len(records), 4)
        self.assertEqual(records[-1].split('\t')[1:], ['backend', NEW, OLD])
        again = self.run_deploy('--rollback', 'backend')
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertIn('BIZAID_BACKEND_TAG=' + NEW, self.env_file.read_text())

    def test_missing_or_unrelated_history_does_not_change_settings(self):
        for content in (None, '20261006\tbackend\t20261001\tdifferent\n', 'invalid\n'):
            if content is not None:
                (self.root / 'deploy-history.log').write_text(content)
            result = self.run_deploy('--rollback', 'backend')
            self.assertEqual(result.returncode, 1)
            self.assertEqual(self.env_file.read_text(), self.original)
        self.assertEqual(self.docker_calls(), [])

    def test_bad_arguments_stop_before_docker_or_env_change(self):
        for args in ((), ('mysql',), ('backend', 'backend'), ('status', 'backend'), ('--rollback',),
                     ('--rollback', 'backend=' + NEW), ('backend=',), ('backend=latest',), ('backend=a;command',), ('--dry-run',)):
            with self.subTest(args=args):
                result = self.run_deploy(*args)
                self.assertEqual(result.returncode, 1)
        self.assertEqual(self.docker_calls(), [])
        self.assertEqual(self.env_file.read_text(), self.original)

    def test_invalid_latest_or_failed_pull_leaves_settings_untouched(self):
        for mode in ('latest_pull_failed', 'missing_label', 'bad_label'):
            result = self.run_deploy('backend', FAKE_MODE=mode)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(self.env_file.read_text(), self.original)
            self.assert_no_secret_output(result)
        self.assertFalse((self.root / 'deploy-history.log').exists())

    def test_failure_after_write_prints_rollback_without_auto_rollback(self):
        for mode in ('config_failed', 'version_pull_failed', 'up_failed', 'not_running', 'wrong_image', 'ps_failed', 'smoke_failed'):
            with self.subTest(mode=mode):
                self.env_file.write_text(self.original)
                result = self.run_deploy('backend=' + NEW, FAKE_MODE=mode)
                self.assertEqual(result.returncode, 1)
                self.assertIn('자동으로 되돌리지 않습니다', result.stderr)
                self.assertIn('되돌리기: bash scripts/deploy.sh backend=' + OLD, result.stderr)
                self.assertIn('BIZAID_BACKEND_TAG=' + NEW, self.env_file.read_text())
                self.assert_no_secret_output(result)
                if mode == 'smoke_failed':
                    self.assertIn('stage=ai_query', result.stderr)
                    self.assertIn('http_status=500', result.stderr)

    def test_duplicate_public_line_and_deploy_lock_fail_before_write(self):
        self.env_file.write_text(self.original + 'BIZAID_BACKEND_TAG=' + OLD + '\n')
        result = self.run_deploy('backend')
        self.assertEqual(result.returncode, 1)
        self.assertIn('중복', result.stderr)
        self.env_file.write_text(self.original)
        (self.root / '.deploy.lock').mkdir()
        result = self.run_deploy('backend')
        self.assertEqual(result.returncode, 1)
        self.assertIn('다른 배포', result.stderr)
        self.assertEqual(self.docker_calls(), [])

    def test_quoted_public_values_are_not_sourced_and_shell_exports_are_ignored(self):
        self.env_file.write_text(self.original.replace('BIZAID_IMAGE_REPO=fixture/deploy', 'export BIZAID_IMAGE_REPO="fixture/deploy" # public')
                                 .replace('BIZAID_BACKEND_TAG=' + OLD, ' BIZAID_BACKEND_TAG = "' + OLD + '"'))
        result = self.run_deploy('backend=' + NEW)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('fixture-jwt # literal', self.env_file.read_text())
        self.assertEqual(self.smoke_calls.read_text().strip(), 'https://fixture.invalid')

    def test_embedded_python_syntax(self):
        code = (ROOT / 'scripts/deploy.sh').read_text().split("<<'PY'\n", 1)[1].rsplit('\nPY', 1)[0]
        compile(code, 'deploy.sh embedded Python', 'exec')

    def test_readiness_timeout_is_bounded_and_never_creates_trial_or_ai_request(self):
        source = (ROOT / 'scripts/deploy.sh').read_text().split("<<'PY'\n", 1)[1].rsplit('\nPY', 1)[0]
        definitions = source.rsplit('\ntry:\n    main()', 1)[0]
        namespace = {}
        with patch.object(sys, 'argv', ['deploy', str(self.root)]):
            exec(compile(definitions, 'deploy definitions', 'exec'), namespace)
        for changes, command in (({'fastapi': ('old', 'new')}, 'docker'), ({'backend': ('old', 'new')}, 'curl')):
            command_mock = Mock(return_value=SimpleNamespace(returncode=1))
            namespace['run'] = command_mock
            with patch('time.sleep') as sleep, self.assertRaises(namespace['DeployError']):
                namespace['smoke']('fixture.invalid', changes)
            self.assertEqual(command_mock.call_count, 30)
            self.assertEqual(sleep.call_count, 29)
            self.assertTrue(all(call.args[0][0] == command for call in command_mock.call_args_list))


if __name__ == '__main__':
    unittest.main()
