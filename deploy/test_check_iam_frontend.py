import hashlib
import http.server
from io import BytesIO
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import threading
import unittest

import check_iam_frontend as guard


def build_files():
    files = {"index.html": b'<script type="module" src="/assets/index-test.js"></script>'}
    menu = ",".join('{to:`%s`,label:`%s`}' % item for item in guard.NAVIGATION.items())
    routes = []
    for path, (component, label) in guard.ROUTES.items():
        filename = component + "-sample.js"
        routes.append("{path:`%s`,component:()=>wrap(()=>import(`./%s`),deps([1])),meta:{fullPage:!0}}" % (path, filename))
        body = f'const title="{label}";'
        if component == "IamRoleTemplatesView":
            body += 'const view={"iam-catalog":unref(!0)};const load=()=>api.listRoles(!0);'
        files["assets/" + filename] = (body + "export {title};").encode()
    files["assets/index-test.js"] = ("const menu=[" + menu + "];const routes=[" + ",".join(routes) + "];").encode()
    return files


def run_cli(*args):
    return subprocess.run([sys.executable, str(Path(guard.__file__)), *args], capture_output=True)


class IamReleaseTests(unittest.TestCase):
    def test_expected_routes_and_receipt(self):
        files = build_files()
        hashes = guard.verify(files.__getitem__)
        self.assertEqual(hashes, {name: hashlib.sha256(data).hexdigest() for name, data in files.items()})

    def test_legacy_route_cannot_be_hidden_by_preloads_or_compatibility_routes(self):
        files = build_files()
        main = files["assets/index-test.js"].replace(b"./PositionWorkbench-sample", b"./PeopleCenter-legacy")
        files["assets/index-test.js"] = main + b'var preload=["PositionWorkbench-sample.js"];'
        with self.assertRaisesRegex(ValueError, "/system/users loads PeopleCenter"):
            guard.verify(files.__getitem__)

    def test_catches_each_partial_rollback(self):
        for old, new, expected in [
            (b"WorkspaceRecords-sample", b"IdentityRecords-old", "loads IdentityRecords"),
            (b"view=inbox", b"view=else", "missing studio navigation"),
            (b"fullPage:!0", b"fullPage:!1", "does not enable fullPage"),
            (b"unref(!0)", b"unref(!1)", "does not enable the studio catalog"),
            (b"api.listRoles(!0)", b"api.listSystemPositions()", "does not enable the studio catalog"),
        ]:
            with self.subTest(marker=old):
                files = {k: v.replace(old, new) for k, v in build_files().items()}
                with self.assertRaisesRegex(ValueError, expected):
                    guard.verify(files.__getitem__)

    def test_rejects_spa_fallback_for_missing_js(self):
        files = build_files()
        files["assets/WorkspaceRecords-sample.js"] = files["index.html"]
        with self.assertRaisesRegex(ValueError, "expected WorkspaceRecords module"):
            guard.verify(files.__getitem__)

    def test_archive_and_dist_agree_and_conflicting_approval_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "assets").mkdir()
            tar = root / "release-web.tar.gz"
            with tarfile.open(tar, "w:gz") as archive:
                for name, data in build_files().items():
                    (root / name).write_bytes(data)
                    member = tarfile.TarInfo("./" + name)
                    member.size = len(data)
                    archive.addfile(member, BytesIO(data))
            approved = root / "approved"
            result = run_cli("--archive", str(tar), "--approve-dir", str(approved))
            self.assertEqual(result.returncode, 0, result.stderr)
            from_dir = run_cli("--dist", str(root), "--approve-dir", str(approved))
            self.assertEqual(from_dir.returncode, 0, from_dir.stderr)
            self.assertEqual(result.stdout, from_dir.stdout)
            receipt, = approved.glob("*.sha256")
            content = receipt.read_bytes()
            self.assertEqual(len(content.splitlines()), 6)
            (root / "assets/WorkspaceRecords-sample.js").write_bytes(
                build_files()["assets/WorkspaceRecords-sample.js"] + b"\n"
            )
            conflict = run_cli("--dist", str(root), "--approve-dir", str(approved))
            self.assertNotEqual(conflict.returncode, 0)
            self.assertIn(b"conflicting existing approval", conflict.stderr)
            self.assertEqual(receipt.read_bytes(), content)
            changed = run_cli("--dist", str(root))
            self.assertEqual(changed.returncode, 0, changed.stderr)
            # Candidate, installed and HTTP checks compare stdout before opening.
            self.assertNotEqual(changed.stdout, result.stdout)

    def test_served_routes_and_scripts_are_public_static_gets(self):
        files = build_files()
        requests = []

        class Static(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(self.path)
                data = files.get(self.path[1:], files["index.html"])
                self.send_response(200)
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        with http.server.ThreadingHTTPServer(("127.0.0.1", 0), Static) as server:
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                url = f"http://127.0.0.1:{server.server_port}"
                self.assertEqual(guard.verify(guard.remote_reader(url)), guard.verify(files.__getitem__))
                for path in guard.NAVIGATION:
                    self.assertIn(path, requests)
                self.assertTrue(all(not path.startswith("/api") for path in requests))
                files["system/users?view=inbox"] = files["index.html"].replace(b"index-test.js", b"index-old.js")
                with self.assertRaisesRegex(ValueError, "different frontend entry"):
                    guard.remote_reader(url)
            finally:
                server.shutdown()
                thread.join()


if __name__ == "__main__":
    unittest.main()
