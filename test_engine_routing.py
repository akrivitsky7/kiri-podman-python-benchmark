"""Regression tests with simulated executables; no container engine required."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('compare_kiri_podman_vms.py')
FAKE = r'''import os, sys, json
from pathlib import Path
name = Path(sys.argv[0]).name
args = sys.argv[1:]
keys = ['DOCKER_HOST','DOCKER_CONTEXT','DOCKER_API_VERSION','DOCKER_TLS','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH','CONTAINER_HOST','CONTAINER_CONNECTION']
assert not any(k in os.environ for k in keys), 'routing environment leaked'
with open(os.environ['TEST_LOG'], 'a') as f:
    f.write(json.dumps([name, args])+'\n')
if name == 'docker':
    assert args[:2] == ['-H', 'unix:///run/kiri/docker.sock'], args
    args = args[2:]
    if args == ['version']:
        if os.environ.get('FAKE_WRONG') == '1':
            print('Server: Podman')
        else:
            print('Client:\n Version: 29.9.2\n API version: 1.47 (downgraded from 1.56)\nServer: Kiri\n Engine:\n  Version: 27.5.1\n  API version: 1.47 (minimum version 1.24)\n Kiri:\n  Version: 0.2.2')
            if os.environ.get('FAKE_WRONG') == '2':
                print('Emulate Docker CLI using podman.', file=sys.stderr)
    elif args[0] == 'info': print('[]')
elif name == 'podman':
    assert args[0] == '--remote=false', args
    args = args[1:]
    if args == ['--version']: print('podman version 5.7.0')
    elif args[0] == 'version':
        print(json.dumps({'Client':{'Version':'5.7.0'}, 'Server': {'Version':'5.7.0'} if os.environ.get('FAKE_WRONG') == '3' else None}))
    elif args[0] == 'info': print('{"host":{"security":{"rootless":true}}}')
else: raise AssertionError('unexpected executable')
if args[0:2] == ['image','inspect']:
    print(json.dumps([{'Id':'sha256:'+'1'*64,'RepoDigests':['alpine@sha256:'+'2'*64],'Architecture':'amd64','Os':'linux'}]))
'''

class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ('docker','podman','kiri'):
            p = self.root / name
            p.write_text('#!'+sys.executable+'\n'+FAKE)
            p.chmod(0o755)
        self.log = self.root/'log'
        self.env = dict(os.environ, PATH=str(self.root)+os.pathsep+os.environ['PATH'], TEST_LOG=str(self.log))
        for key in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_API_VERSION','DOCKER_TLS','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH','CONTAINER_HOST','CONTAINER_CONNECTION'):
            self.env[key]='deliberately-conflicting'
    def call(self, *args, wrong=None):
        env = self.env.copy()
        if wrong: env['FAKE_WRONG']=wrong
        return subprocess.run([sys.executable,str(SCRIPT),*args],env=env,capture_output=True,text=True)
    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]
    def test_verify_kiri_no_pull(self):
        r=self.call('--engine','kiri','--kiri-cli',str(self.root/'docker'),'--verify-only')
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('Engine version: 0.2.2',r.stdout)
        self.assertEqual([a[1][2] for a in self.calls()],['version','info','ps'])
    def test_verify_podman_no_pull(self):
        r=self.call('--engine','podman','--verify-only')
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('Engine version: 5.7.0',r.stdout)
        self.assertEqual([a[1][1] for a in self.calls()],['--version','version','info','ps'])
    def test_reject_wrong_server(self):
        r=self.call('--engine','kiri','--kiri-cli',str(self.root/'docker'),wrong='1')
        self.assertNotEqual(r.returncode,0)
        self.assertIn('did not identify itself',r.stderr)
        self.assertEqual(len(self.calls()),1)
    def test_reject_emulation_warning(self):
        r=self.call('--engine','kiri','--kiri-cli',str(self.root/'docker'),wrong='2')
        self.assertNotEqual(r.returncode,0)
        self.assertIn('compatibility wrapper',r.stderr)
        self.assertEqual(len(self.calls()),1)
    def test_reject_remote_podman(self):
        r=self.call('--engine','podman',wrong='3')
        self.assertNotEqual(r.returncode,0)
        self.assertIn('separate server',r.stderr)
        self.assertEqual(len(self.calls()),2)
    def test_full_suites_and_comparison(self):
        files=[]
        for engine in ('kiri','podman'):
            out=self.root/(engine+'.json'); files.append(out)
            opts=['--kiri-cli',str(self.root/'docker')] if engine=='kiri' else []
            r=self.call('--engine',engine,*opts,'--runs','2','--warmups','1','--output',str(out))
            self.assertEqual(r.returncode,0,r.stderr)
            data=json.loads(out.read_text())
            self.assertEqual(data['schema_version'],2)
            self.assertEqual(data['benchmark_version'],'1.2.0')
            self.assertTrue(data['engine_routing']['identity_verified'])
            self.assertIn('DOCKER_HOST',data['engine_routing']['cleared_environment_variables'])
            self.assertEqual(data['benchmarks']['ps']['count'],2)
            self.assertEqual(data['benchmarks']['run']['count'],2)
            self.assertEqual(data['benchmark_commands']['run'][-6:],['run','--rm','--network','none','docker.io/library/alpine:3.22','/bin/true'])
        r=self.call('--compare',*(str(p) for p in files))
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('BENCHMARK COMPARISON',r.stdout)
        # Schema 1/2 results without new metadata are still accepted, with a warning.
        data=json.loads(files[0].read_text()); data.pop('engine_routing'); data['benchmark_version']='1.1.0'
        files[0].write_text(json.dumps(data))
        r=self.call('--compare',*(str(p) for p in files))
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('isolated routing verification not recorded',r.stderr)

if __name__=='__main__': unittest.main()
