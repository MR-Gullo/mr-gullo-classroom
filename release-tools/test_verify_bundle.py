"""Negative release tests: unsafe or stale artifacts must never become deployable."""
import copy
import importlib.util
import json
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
module = ROOT / 'scripts/tester-updates/verify_bundle.py'
if not module.exists():
    module = ROOT / 'release-tools/verify_bundle.py'
spec = importlib.util.spec_from_file_location('bundle', module)
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.archive = Path(self.temp.name) / 'app.zip'
        self.files = {
            'index.html': b'<meta name="robots" content="noindex, nofollow"><link rel="manifest" href="/mr-gullo-classroom/manifest.webmanifest"><script src="/mr-gullo-classroom/assets/index-test.js"></script>',
            'manifest.webmanifest': json.dumps({'start_url': './', 'scope': './', 'display': 'standalone'}).encode(),
            'sw.js': b'worker', 'icons/192x192.png': b'png', 'icons/512x512.png': b'png',
            'third-party-notices.txt': b'notices', 'assets/index-test.js': b'app',
            'assets/classroom_engine_bg-test.wasm': b'wasm', 'assets/sqlite3-test.wasm': b'wasm'}
        self.write_zip()
        self.baseline_sha = 'a' * 64
        self.receipt = {'schemaVersion': 1, 'kind': 'candidate', 'tag': 'v0.1.0-rc.2',
                        'repository': b.REPO, 'site': b.SITE, 'sourceCommit': 'b' * 40,
                        'createdAt': '2026-10-22T00:00:00+00:00',
                        'sha256': b.digest(self.archive.read_bytes()), 'bytes': self.archive.stat().st_size,
                        'files': {n: b.digest(data) for n, data in self.files.items()},
                        'automatedChecks': {'npmCheck': True, 'package': True, 'releaseGuards': True},
                        'rollbackTo': self.baseline_sha,
                        'qa': {'checks': {n: True for n in b.QA}, 'evidenceSha256': 'c' * 64}}

    def write_zip(self, extra=None):
        with zipfile.ZipFile(self.archive, 'w') as z:
            for name, data in self.files.items():
                z.writestr(name, data)
            if extra:
                z.writestr(*extra)

    def test_valid_candidate_and_materialization(self):
        files = b.verify_receipt(self.archive, self.receipt)
        out = Path(self.temp.name) / 'site'
        b.materialize(files, self.receipt, out)
        self.assertEqual((out / 'assets/index-test.js').read_bytes(), b'app')
        self.assertEqual(json.loads((out / 'version.json').read_text())['sha256'], self.receipt['sha256'])
        with self.assertRaises(FileExistsError):
            b.materialize(files, self.receipt, out)

    def test_tampering_and_inventory(self):
        self.archive.write_bytes(self.archive.read_bytes() + b'changed')
        with self.assertRaisesRegex(ValueError, 'tested receipt'):
            b.verify_receipt(self.archive, self.receipt)
        self.write_zip()
        receipt = copy.deepcopy(self.receipt)
        receipt['files'].pop('sw.js')
        with self.assertRaisesRegex(ValueError, 'inventory'):
            b.verify_receipt(self.archive, receipt)

    def test_traversal_private_files_and_duplicates(self):
        for path in ('../secret.txt', '/absolute', 'assets/../x.js', 'assets\\x.js',
                     'backup.classroom', 'db/workspace.sqlite', '.env', 'src/App.tsx'):
            with self.subTest(path=path):
                self.write_zip((path, b'x'))
                with self.assertRaises(ValueError):
                    b.inspect_archive(self.archive)
        self.write_zip(('ASSETS/INDEX-TEST.JS', b'other'))
        with self.assertRaisesRegex(ValueError, 'case-colliding'):
            b.inspect_archive(self.archive)

    def test_symlink_refused(self):
        link = zipfile.ZipInfo('assets/link.js')
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        self.write_zip((link, b'../../outside'))
        with self.assertRaisesRegex(ValueError, 'link'):
            b.inspect_archive(self.archive)

    def test_no_index_base_path_and_runtime_required(self):
        original = dict(self.files)
        for change in ('noindex', '/mr-gullo-classroom/assets/', 'engine'):
            self.files = dict(original)
            if change == 'engine':
                del self.files['assets/classroom_engine_bg-test.wasm']
            else:
                self.files['index.html'] = self.files['index.html'].replace(change.encode(), b'wrong')
            self.write_zip()
            with self.assertRaises(ValueError):
                b.inspect_archive(self.archive)

    def test_unchecked_and_unreviewed_refused(self):
        for key in ('npmCheck', 'package', 'releaseGuards'):
            receipt = copy.deepcopy(self.receipt)
            receipt['automatedChecks'][key] = False
            with self.assertRaisesRegex(ValueError, 'automated'):
                b.verify_receipt(self.archive, receipt)

    def test_prepared_but_unreviewed_receipt_is_refused_clearly(self):
        receipt = dict(self.receipt, qa=None)
        with self.assertRaisesRegex(ValueError, 'manual QA is incomplete'):
            b.verify_receipt(self.archive, receipt)
        for key in b.QA:
            receipt = copy.deepcopy(self.receipt)
            receipt['qa']['checks'][key] = False
            with self.assertRaisesRegex(ValueError, 'manual QA'):
                b.verify_receipt(self.archive, receipt)

    def test_private_or_unexpected_receipt_fields_refused(self):
        receipt = dict(self.receipt, privateNotes='not for publication')
        with self.assertRaisesRegex(ValueError, 'public fields'):
            b.verify_receipt(self.archive, receipt)
        receipt = copy.deepcopy(self.receipt)
        receipt['qa']['rawEvidence'] = 'must remain local'
        with self.assertRaisesRegex(ValueError, 'only check results'):
            b.verify_receipt(self.archive, receipt)

    def test_baseline_cannot_be_forged(self):
        baseline = copy.deepcopy(self.receipt)
        baseline['kind'] = 'adopted-baseline'
        b.verify_receipt(self.archive, baseline, baseline)
        with self.assertRaisesRegex(ValueError, 'trusted baseline'):
            b.verify_receipt(self.archive, baseline)
        forged = dict(baseline, sourceCommit='d' * 40)
        with self.assertRaises(ValueError):
            b.verify_receipt(self.archive, forged, baseline)

    def test_stale_promotion_and_data_unsafe_rollback_refused(self):
        b.check_transition(self.receipt, {'sha256': self.baseline_sha}, 'promote', self.baseline_sha)
        for current, expected in (({'sha256': 'd' * 64}, self.baseline_sha),
                                  ({'sha256': self.baseline_sha}, ''),
                                  ({'sha256': self.baseline_sha}, 'd' * 64)):
            with self.assertRaises(ValueError):
                b.check_transition(self.receipt, current, 'promote', expected)
        current = {'sha256': 'd' * 64, 'rollbackTo': self.receipt['sha256']}
        b.check_transition(self.receipt, current, 'rollback', 'd' * 64)
        with self.assertRaisesRegex(ValueError, 'data-safe'):
            b.check_transition(self.receipt, {'sha256': 'd' * 64}, 'rollback', 'd' * 64)

    def test_malicious_tags_and_cross_repo_receipts(self):
        for tag in ('--help', 'v1.0.0;echo nope', '../main', 'v0.1.0-rc.2\nmain'):
            with self.assertRaises(ValueError):
                b.valid_tag(tag)
        receipt = dict(self.receipt, repository='other/repository')
        with self.assertRaisesRegex(ValueError, 'different repository'):
            b.verify_receipt(self.archive, receipt)

    def test_archive_expansion_limit(self):
        with zipfile.ZipFile(self.archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr('assets/oversized.js', b'x' * (16 * 1024 * 1024 + 1))
        with self.assertRaisesRegex(ValueError, 'limits'):
            b.inspect_archive(self.archive)

    def test_source_and_qa_binding(self):
        receipt = copy.deepcopy(self.receipt)
        receipt['sourceCommit'] = 'main'
        with self.assertRaisesRegex(ValueError, 'source commit'):
            b.verify_receipt(self.archive, receipt)
        receipt = copy.deepcopy(self.receipt)
        receipt['qa']['evidenceSha256'] = ''
        with self.assertRaisesRegex(ValueError, 'evidence fingerprint'):
            b.verify_receipt(self.archive, receipt)

    def test_already_live_and_wrong_promotion_parent(self):
        with self.assertRaisesRegex(ValueError, 'already live'):
            b.check_transition(self.receipt, {'sha256': self.receipt['sha256']},
                               'promote', self.receipt['sha256'])
        with self.assertRaisesRegex(ValueError, 'current live build'):
            b.check_transition(self.receipt, {'sha256': 'd' * 64}, 'promote', 'd' * 64)

    def test_verify_cannot_make_a_transition(self):
        # Verification can inspect an old baseline without accepting it for promotion.
        b.check_transition(self.receipt, {'sha256': 'd' * 64}, 'verify', '')
        baseline = dict(self.receipt, kind='adopted-baseline')
        with self.assertRaises(ValueError):
            b.check_transition(baseline, {'sha256': self.baseline_sha}, 'promote', self.baseline_sha)


if __name__ == '__main__':
    unittest.main()
