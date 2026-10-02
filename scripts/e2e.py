#!/usr/bin/env python3
"""Sign each fictional person in through oauth2-proxy and Dex, the way a
browser does, and check what Cartograph lets them see and do.

    scripts/e2e.py [http://localhost:4180]

Runs against `just up`. Exits non-zero, naming each failure, when
anything is not as config/access.yaml and the directory say it should
be. Standard library only.
"""
import http.client
import http.cookiejar
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:4180"
PASSWORD = "try-cartograph"
failures = []


def check(what, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + what + (f" ({detail})" if detail and not ok else ""))
    if not ok:
        failures.append(what)


class Browser:
    """A cookie jar and the redirects a browser follows."""

    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def open(self, url, data=None, method=None, body=None):
        headers = {}
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with self.opener.open(req, timeout=15) as resp:
                return resp.status, resp.geturl(), resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, e.geturl(), e.read().decode("utf-8", "replace")

    def sign_in(self, email):
        """Through oauth2-proxy to Dex's login form, and back."""
        status, url, page = self.open(BASE + "/")
        form = re.search(r'<form[^>]*action="([^"]+)"', page)
        if not form:
            raise RuntimeError(f"no login form at {url} ({status})")
        action = urllib.parse.urljoin(url, form.group(1).replace("&amp;", "&"))
        fields = urllib.parse.urlencode({"login": email, "password": PASSWORD}).encode()
        status, url, _ = self.open(action, data=fields)
        if not url.startswith(BASE):
            raise RuntimeError(f"sign-in for {email} ended at {url} ({status})")

    def api(self, method, path, body=None):
        status, _, text = self.open(BASE + "/api/v1" + path, method=method, body=body)
        try:
            return status, json.loads(text) if text else None
        except json.JSONDecodeError:
            return status, text

    def cookie_header(self):
        return "; ".join(f"{c.name}={c.value}" for c in self.jar)


def as_person(email):
    b = Browser()
    b.sign_in(email)
    return b


def save_working(b, kind, id):
    """Save a manifest's working copy back as it is: a write that changes
    nothing, so only the access decision is tested."""
    status, view = b.api("GET", f"/manifests/{kind}/{id}")
    if status != 200:
        return status
    status, _ = b.api("PUT", f"/manifests/{kind}/{id}/working", {"yaml": view["yaml"]})
    return status


def sync_upgrade(b):
    """The sync socket, through oauth2-proxy and nginx: 101 when the
    WebSocket upgrade passes every hop."""
    u = urllib.parse.urlparse(BASE)
    conn = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=10)
    conn.request("GET", "/api/v1/sync", headers={
        "Cookie": b.cookie_header(), "Connection": "Upgrade", "Upgrade": "websocket",
        "Sec-WebSocket-Version": "13", "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ==",
    })
    status = conn.getresponse().status
    conn.close()
    return status


def main():
    # Before anyone signs in, Cartograph is out of reach.
    status, url, _ = Browser().open(BASE + "/api/v1/session")
    check("an unsigned request is sent to sign in, never to Cartograph", "/dex/" in url or status in (401, 403), f"{status} {url}")

    ada = as_person("ada@example.org")
    status, s = ada.api("GET", "/session")
    a = (s or {}).get("access") or {}
    check("the administrator signs in with their directory name", status == 200 and s.get("name") == "Ada Mensah", f"{status} {s}")
    check("the administrator's groups make them reader and administrator", a.get("roles") == ["reader", "administrator"], a.get("roles"))
    status, people = ada.api("GET", "/access/people")
    check("the administrator reads the access list", status == 200 and any(p["email"] == "ada@example.org" for p in people["people"]), status)
    status, teams = ada.api("GET", "/manifests/Team")
    names = sorted(t["name"] for t in (teams if isinstance(teams, list) else teams.get("items", [])))
    check("the mapped teams exist", names == ["Assessment", "Curriculum division", "Early grades", "Planning"], names)
    check("the sync socket upgrades through the proxy", sync_upgrade(ada) == 101)
    status, _, page = ada.open(BASE + "/")
    check("the interface is served through the proxy", status == 200 and "<title>" in page, status)

    lee = as_person("lee@example.org")
    status, s = lee.api("GET", "/session")
    a = (s or {}).get("access") or {}
    check("a contributor's teams reach the teams beneath them", a.get("teams") == ["curriculum-division"] and set(a.get("reach", [])) == {"curriculum-division", "early-grades"}, a)
    check("a contributor may write their teams' projects", a.get("scopes", {}).get("Project") == "teams", a.get("scopes", {}).get("Project"))
    check("a contributor changes a project of a team beneath theirs", save_working(lee, "Project", "coach-early-grade-teachers") in (200, 204))
    check("a contributor is refused another team's project", save_working(lee, "Project", "grade-two-reading-check") == 403)
    check("a contributor may not read the access list", lee.api("GET", "/access/people")[0] == 403)

    sam = as_person("sam@example.org")
    check("the assessment analyst changes their team's project", save_working(sam, "Project", "grade-two-reading-check") in (200, 204))
    check("the assessment analyst is refused the curriculum division's project", save_working(sam, "Project", "revise-reading-curriculum") == 403)

    ren = as_person("ren@example.org")
    status, s = ren.api("GET", "/session")
    sc = ((s or {}).get("access") or {}).get("scopes", {})
    check("a strategy editor may write goals and not projects", sc.get("Goal") == "all" and sc.get("Project") == "none", sc)
    check("a strategy editor is refused a project", save_working(ren, "Project", "coach-early-grade-teachers") == 403)

    noor = as_person("noor@example.org")
    status, s = noor.api("GET", "/session")
    check("a reader reads", noor.api("GET", "/manifests/Project/coach-early-grade-teachers")[0] == 200)
    check("a reader writes nothing", save_working(noor, "Project", "coach-early-grade-teachers") == 403 and s.get("canWrite") is False, s)

    # An administrator grants the reader the strategy editor role, and
    # takes it back; the directory's part is untouched.
    status, p = ada.api("PUT", "/access/people/noor@example.org", {"roles": ["strategyEditor"], "teams": []})
    check("an administrator grants a role", status == 200 and p["roles"] == ["strategyEditor"] and p["directoryRoles"] == ["reader"], p)
    status, s = noor.api("GET", "/session")
    check("the grant takes effect at once", s["access"]["scopes"].get("Goal") == "all", s["access"]["scopes"].get("Goal"))
    ada.api("PUT", "/access/people/noor@example.org", {"roles": [], "teams": []})
    check("an administrator may not remove themselves", ada.api("DELETE", "/access/people/ada@example.org")[0] == 409)

    vic = as_person("vic@example.org")
    status, s = vic.api("GET", "/session")
    check("someone the directory gives no role is not listed", status == 200 and s["access"]["listed"] is False, s)
    check("and reads nothing", vic.api("GET", "/manifests/Project/coach-early-grade-teachers")[0] == 403)

    print()
    if failures:
        print(f"{len(failures)} failed")
        sys.exit(1)
    print("every check passed")


if __name__ == "__main__":
    main()
