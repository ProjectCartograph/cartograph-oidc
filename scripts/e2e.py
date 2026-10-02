#!/usr/bin/env python3
"""Sign each fictional person in through oauth2-proxy and Dex, the way a
browser does, and check what Cartograph lets them see and do.

    scripts/e2e.py [http://localhost:4180]

Runs against `just up`. Exits non-zero, naming each failure, when
anything is not as config/access.yaml and the directory say it should
be. Standard library only.
"""
import base64
import hashlib
import html
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


VERIFIER = "e2e-code-verifier-of-at-least-forty-three-characters"
REDIRECT = "http://127.0.0.1:33418/callback"


def connect_agent(b, name="Claude"):
    """MCP's browser flow, as a client runs it with Cartograph as the
    authorization server: register, ask the signed-in person, exchange
    the code. Returns (status of the consent page, access token or None)."""
    reg = json.loads(urllib.request.urlopen(urllib.request.Request(
        BASE + "/oauth/register", method="POST", headers={"Content-Type": "application/json"},
        data=json.dumps({"client_name": name, "redirect_uris": ["http://127.0.0.1/callback"]}).encode()), timeout=15).read())
    challenge = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).rstrip(b"=").decode()
    query = urllib.parse.urlencode({"response_type": "code", "client_id": reg["client_id"], "redirect_uri": REDIRECT, "state": "e2e",
                                    "code_challenge": challenge, "code_challenge_method": "S256", "resource": BASE + "/api/v1/mcp"})
    status, _, page = b.open(BASE + "/oauth/authorize?" + query)
    consent = re.search(r'name="consent" value="([^"]+)"', page)
    if status != 200 or not consent:
        return status, None
    # The answer redirects to the client, which is not listening: read
    # the redirect rather than follow it.
    class Stay(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args):
            return None
    stay = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(b.jar), Stay())
    form = urllib.parse.urlencode({"consent": html.unescape(consent.group(1)), "decision": "allow"}).encode()
    try:
        stay.open(urllib.request.Request(BASE + "/oauth/authorize", data=form), timeout=15)
        return status, None
    except urllib.error.HTTPError as e:
        location = urllib.parse.urlparse(e.headers.get("Location", ""))
    code = urllib.parse.parse_qs(location.query).get("code", [""])[0]
    tokens = json.loads(urllib.request.urlopen(urllib.request.Request(BASE + "/oauth/token", data=urllib.parse.urlencode({
        "grant_type": "authorization_code", "code": code, "client_id": reg["client_id"],
        "redirect_uri": REDIRECT, "code_verifier": VERIFIER}).encode()), timeout=15).read())
    return status, tokens.get("access_token")


def mcp(token, tool, args=None, method="tools/call"):
    """One MCP request with an agent's token, and nothing else: stateless,
    no handshake, no session cookie."""
    params = {"name": tool, "arguments": args or {}} if method == "tools/call" else {}
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-11-25"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(BASE + "/api/v1/mcp", method="POST", headers=headers,
                                 data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode())
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read())
            return resp.status, body.get("result") or body.get("error"), ""
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), e.headers.get("WWW-Authenticate", "")


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

    # Agents (cartograph-engine docs/adr/0016): contributors and strategy
    # editors may connect one, through the browser, with Cartograph as the
    # authorization server; it reads, drafts and proposes, and its person
    # decides.
    status, _, text = Browser().open(BASE + "/.well-known/oauth-authorization-server")
    check("an MCP client finds the authorization server without signing in", status == 200 and "registration_endpoint" in text, status)
    status, _, challenge = mcp(None, "", method="tools/list")
    check("an agent with no token is told where to sign in", status == 401 and "resource_metadata=" in challenge, f"{status} {challenge}")
    forged = urllib.request.Request(BASE + "/api/v1/mcp", method="POST", data=b"{}",
                                    headers={"Content-Type": "application/json", "X-Forwarded-Email": "ada@example.org", "X-Forwarded-User": "ada@example.org"})
    try:
        urllib.request.urlopen(forged, timeout=15)
        forged_status = 200
    except urllib.error.HTTPError as e:
        forged_status = e.code
    check("identity headers sent from outside count for nothing", forged_status == 401, forged_status)
    status, token = connect_agent(lee)
    check("a contributor connects an agent through the browser", status == 200 and token, status)
    status, result, _ = mcp(token, "", method="tools/list")
    tools = [t["name"] for t in (result or {}).get("tools", [])] if isinstance(result, dict) else []
    check("the agent connects with its token alone", status == 200 and "propose_save" in tools, f"{status} {result}")
    status, view = lee.api("GET", "/manifests/Project/coach-early-grade-teachers")
    manifest = view["manifest"]
    versions_before = len(lee.api("GET", "/manifests/Project/coach-early-grade-teachers/versions")[1])
    manifest["spec"]["summary"]["problems"][0]["problem"]["situation"] += " Drafted with an agent."
    status, result, _ = mcp(token, "save_draft", {"kind": "Project", "id": "coach-early-grade-teachers", "manifest": manifest})
    check("the agent drafts its person's team's project", status == 200 and not result.get("isError"), result)
    status, result, _ = mcp(token, "save_draft", {"kind": "Project", "id": "grade-two-reading-check", "manifest": lee.api("GET", "/manifests/Project/grade-two-reading-check")[1]["manifest"]})
    check("the agent has no more access than its person", status == 200 and result.get("isError"), result)
    # The seed project meets few of its checks. An agent may not propose
    # past them (cartograph-engine docs/adr/0017); it names each one it
    # cannot meet, with why, and its person reads those reasons.
    status, result, _ = mcp(token, "propose_save", {"kind": "Project", "id": "coach-early-grade-teachers", "reason": "describe the situation"})
    check("the agent may not propose past open checks", status == 200 and result.get("isError") and "still open" in json.dumps(result), result)
    status, report, _ = mcp(token, "checks", {"kind": "Project", "id": "coach-early-grade-teachers"})
    open_checks = {c["id"]: "Lee has not decided this yet" for c in (report or {}).get("structuredContent", {}).get("open", [])}
    status, result, _ = mcp(token, "propose_save", {"kind": "Project", "id": "coach-early-grade-teachers", "reason": "describe the situation", "openChecks": open_checks})
    check("the agent proposes, naming each check it leaves open", status == 200 and not result.get("isError") and len(open_checks) > 0, result)
    versions_now = len(lee.api("GET", "/manifests/Project/coach-early-grade-teachers/versions")[1])
    check("nothing the agent did is a version yet", versions_now == versions_before, f"{versions_before} -> {versions_now}")
    status, mine = lee.api("GET", "/proposals")
    check("the proposal waits for its person, with the agent's reasons", status == 200 and len(mine) == 1 and mine[0]["agent"] == "Claude"
          and len(mine[0].get("waivers", [])) == len(open_checks), mine)
    pid = mine[0]["id"] if mine else ""
    check("nobody else decides it", sam.api("POST", f"/proposals/{pid}/accept", {})[0] == 403)
    status, decided = lee.api("POST", f"/proposals/{pid}/accept", {"reason": "reads right"})
    status_v, versions = lee.api("GET", "/manifests/Project/coach-early-grade-teachers/versions")
    last = versions[-1] if status_v == 200 and versions else {}
    check("its person accepts, and it is saved as theirs", status == 200 and last.get("actor") == "lee@example.org" and "proposed by Claude" in last.get("reason", ""), last)
    status, grants = lee.api("GET", "/agents")
    # Agents disconnected by an earlier run stay listed, as disconnected.
    grants = [g for g in grants if not g.get("revokedAt")] if status == 200 else []
    check("its person sees the agent connected", len(grants) == 1 and grants[0]["label"] == "Claude" and grants[0].get("lastUsed"), grants)
    check("nobody else disconnects it", sam.api("DELETE", f"/agents/{grants[0]['id'] if grants else ''}")[0] == 403)
    check("its person disconnects it", lee.api("DELETE", f"/agents/{grants[0]['id'] if grants else ''}")[0] == 204)
    check("and its token ends at once", mcp(token, "", method="tools/list")[0] == 401)
    check("a reader may not connect one", connect_agent(noor)[0] == 403)
    check("an administrator may not, as the mapping allows none", connect_agent(ada)[0] == 403)

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
