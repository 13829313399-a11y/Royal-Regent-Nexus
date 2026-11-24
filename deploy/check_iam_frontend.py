"""Verify the production IAM workspace from the static files actually being shipped."""

import argparse
from contextlib import ExitStack
import hashlib
from html.parser import HTMLParser
from io import BytesIO
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, Request


ROUTES = {
    "/system/users": ("PositionWorkbench", "办理大厅"),
    "/system/iam/audit": ("WorkspaceRecords", "审计记录"),
    "/system/iam/roles": ("IamRoleTemplatesView", "权限方案库"),
    "/account/position": ("MyPositionPanel", "我的岗位与权限"),
}
NAVIGATION = {
    "/system/users?view=inbox": "办理大厅",
    "/system/users?view=people": "人员与权限",
    "/system/iam/roles": "权限方案库",
    "/system/iam/audit": "审计记录",
}
QUOTES = r"""["'`]"""
ENABLED = r"(?:!0|true)"
ASSET = r"[\w-]+\.js"


def literal(value):
    return QUOTES + re.escape(value) + QUOTES


class EntryParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.modules = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script" and attrs.get("type") == "module":
            self.modules.append(attrs.get("src") or "")

    def entry(self, html):
        self.feed(html.decode("utf-8"))
        self.close()
        if len(self.modules) != 1 or not re.fullmatch(r"/assets/" + ASSET, self.modules[0]):
            raise ValueError("index.html must load one local /assets/ JavaScript module")
        return self.modules[0][1:]


def route_chunk(main, path):
    # Anchor the import to this route's selected component. The preload dependency
    # table and the advanced compatibility route can contain *both* page names.
    pattern = (r"\bpath\s*:\s*" + literal(path)
               + r"\s*,\s*(?:name\s*:\s*" + QUOTES + r"[\w-]+" + QUOTES + r"\s*,\s*)?"
               + r"component\s*:\s*\(\)\s*=>\s*(?:[\w$]+\(\s*\(\)\s*=>\s*)?"
               + r"import\(\s*" + QUOTES + r"\./(" + ASSET + r")" + QUOTES
               + r"\s*\)[^{};]*?,\s*meta\s*:\s*\{([^{}]*)\}")
    matches = re.findall(pattern, main)
    if len(matches) != 1:
        raise ValueError(f"{path} has no unique compiled lazy route")
    filename, meta = matches[0]
    expected, _ = ROUTES[path]
    if not re.fullmatch(re.escape(expected) + r"-[\w-]+\.js", filename):
        raise ValueError(f"{path} loads {filename}, expected {expected}")
    if not re.search(r"\bfullPage\s*:\s*" + ENABLED + r"\s*(?:,|$)", meta):
        raise ValueError(f"{path} does not enable fullPage")
    return "assets/" + filename


def verify(read):
    checksums = {}

    def asset(path):
        data = read(path)
        checksums[path] = hashlib.sha256(data).hexdigest()
        return data

    entry = EntryParser().entry(asset("index.html"))
    main = asset(entry).decode("utf-8")
    errors = []
    for path, label in NAVIGATION.items():
        nav = r"\bto\s*:\s*" + literal(path) + r"\s*,\s*label\s*:\s*" + literal(label)
        if not re.search(nav, main):
            errors.append(f"missing studio navigation: {path} ({label})")
    for path, (component, label) in ROUTES.items():
        try:
            chunk = asset(route_chunk(main, path)).decode("utf-8")
            if chunk.lstrip().startswith("<") or not re.search(r"\bexport\s*(?:\{|default\b)", chunk) or label not in chunk:
                raise ValueError(f"{path} did not load the expected {component} module")
            if path == "/system/iam/roles":
                # The old render also includes the catalog's Chinese label. Check
                # the actual Vue branch and the selected catalog API separately.
                cls = literal("iam-catalog") + r"\s*:\s*(?:[\w$]+\(\s*)?" + ENABLED + r"\s*\)?\s*\}"
                if not re.search(cls, chunk) or not re.search(r"\.listRoles\(\s*" + ENABLED + r"\s*\)", chunk):
                    raise ValueError(f"{path} does not enable the studio catalog and its role query")
        except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
            errors.append(str(error))
    if errors:
        raise ValueError("\n".join(errors))
    return checksums


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def remote_reader(url):
    if urlsplit(url).scheme not in ("http", "https") or urlsplit(url).path not in ("", "/"):
        raise ValueError("--url requires the final HTTP(S) site origin")
    origin = url.rstrip("/")
    opener = build_opener(NoRedirect())

    def read(path):
        request = Request(origin + "/" + path, headers={"Cache-Control": "no-cache"})
        with opener.open(request, timeout=20) as response:
            return response.read()

    index = read("index.html")
    entry = EntryParser().entry(index)
    for path in ["/system/users", *NAVIGATION, "/account/position"]:
        if EntryParser().entry(read(path[1:])) != entry:
            raise ValueError(f"{path} serves a different frontend entry")
    return lambda path: index if path == "index.html" else read(path)


def docker(*args):
    return subprocess.check_output(["docker", *args])


def container_reader(container):
    def read(path):
        data = docker("cp", f"{container}:/usr/share/nginx/html/{path}", "-")
        with tarfile.open(fileobj=BytesIO(data)) as archive:
            members = archive.getmembers()
            if len(members) != 1 or not members[0].isfile():
                raise ValueError(f"expected one Nginx file: {path}")
            return archive.extractfile(members[0]).read()
    return read


def archive_reader(archive):
    files = {}
    for member in archive.getmembers():
        path = member.name.removeprefix("./")
        if path == "index.html" or re.fullmatch("assets/" + ASSET, path):
            if path in files or not member.isfile():
                raise ValueError(f"duplicate or non-regular web asset: {path}")
            files[path] = member

    def read(path):
        if path not in files:
            raise ValueError(f"archive is missing {path}")
        return archive.extractfile(files[path]).read()
    return read


def write_receipt(path, checksums, *, immutable=False):
    data = "".join(f"{digest}  {name}\n" for name, digest in checksums.items()).encode("ascii")
    fd, name = tempfile.mkstemp(dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(data)
        temporary.chmod(0o644)
        if immutable:
            # Never invalidate a previous approval, including concurrent releases
            # claiming the same index hash with different component bytes.
            try:
                os.link(temporary, path)
            except FileExistsError:
                if path.read_bytes() != data:
                    raise ValueError(f"conflicting existing approval for {path.name}")
        else:
            os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--dist", type=Path, help="built Nginx document root")
    source.add_argument("--archive", type=Path, help="prebuilt tar archive, with index.html at its root")
    source.add_argument("--url", help="HTTP(S) origin; only public HTML and referenced JS are fetched")
    source.add_argument("--container", help="read the actual Nginx files from a running or stopped container")
    source.add_argument("--image", help="verify a candidate image without starting it")
    receipt = parser.add_mutually_exclusive_group()
    receipt.add_argument("--write-checksums", type=Path, help="write a sha256sum-compatible file on success")
    receipt.add_argument("--approve-dir", type=Path, help="publish a verified receipt named <index-sha256>.sha256")
    args = parser.parse_args()
    try:
        with ExitStack() as stack:
            if args.dist:
                read = lambda path: (args.dist / path).read_bytes()
            elif args.archive:
                read = archive_reader(stack.enter_context(tarfile.open(args.archive)))
            elif args.url:
                read = remote_reader(args.url)
            else:
                container = args.container
                if args.image:
                    container = docker("create", "--network", "none", args.image).decode().strip()
                    stack.callback(docker, "rm", "-v", container)
                read = container_reader(container)
            checksums = verify(read)
        index_sha = checksums["index.html"]
        if args.approve_dir:
            args.approve_dir.mkdir(parents=True, exist_ok=True)
            write_receipt(args.approve_dir / f"{index_sha}.sha256", checksums, immutable=True)
        elif args.write_checksums:
            write_receipt(args.write_checksums, checksums)
        print(f"IAM studio release verified: index.html {index_sha}")
        for path, digest in checksums.items():
            print(f"{digest}  {path}")
        return 0
    except (ValueError, OSError, tarfile.TarError, subprocess.CalledProcessError) as error:
        print(f"IAM studio release rejected: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
