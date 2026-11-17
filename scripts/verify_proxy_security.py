"""Exercise the shipped Nginx boundary with two real, distinct Docker clients.

Run only after switching the Compose API to carerank_test. Account credentials
are inherited from the E2E environment; never printed or placed in source.
"""

import json
import os
import subprocess
import uuid
from sqlalchemy.engine import make_url


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True).strip()


def main():
    assert make_url(os.environ["CARERANK_CI_DATABASE_URL"]).database == "carerank_test"
    api_id = docker("compose", "ps", "-q", "api")
    web_id = docker("compose", "ps", "-q", "web")
    api = json.loads(docker("inspect", api_id))[0]
    # Verify the running API itself, not just the caller's declared target.
    env = dict(entry.split("=", 1) for entry in api["Config"]["Env"])
    assert make_url(env["DATABASE_URL"]).database == "carerank_test"
    assert make_url(env["DATABASE_URL"]).username != "carerank"
    web = json.loads(docker("inspect", web_id))[0]
    network = next(n for n in web["NetworkSettings"]["Networks"] if n.endswith("_proxy"))
    clients = ["carerank-proxy-" + uuid.uuid4().hex[:12] for _ in range(2)]
    request = '''
import json, os, urllib.request, urllib.error

def login(username, password, forged="203.0.113.99"):
    request = urllib.request.Request("http://web:8080/api/auth/login",
        data=json.dumps({"username": username, "password": password}).encode(),
        headers={"Content-Type": "application/json", "Origin": "http://127.0.0.1:8080",
                 "X-CareRank-Client-IP": forged, "X-Forwarded-For": forged,
                 "Forwarded": "for=" + forged})
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=15) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
'''
    try:
        for client in clients:
            docker("run", "-d", "--name", client, "--network", network,
                   "-e", "E2E_USERNAME", "-e", "E2E_PASSWORD", api["Config"]["Image"], "sleep", "300")
        blocked = request + '''
for i in range(30):
    assert login("proxy-abuse-" + str(i), "incorrect") == 401
for i in range(20):
    assert login("blocked-" + str(i), "incorrect", "203.0.113." + str(i + 1)) == 429
print("Blocked source cannot bypass its limit with forged forwarding headers")
'''
        independent = request + '''
assert login(os.environ["E2E_USERNAME"], os.environ["E2E_PASSWORD"]) == 200
print("Independent client can authenticate through the same Nginx proxy")
'''
        print(docker("exec", clients[0], "python", "-c", blocked))
        print(docker("exec", clients[1], "python", "-c", independent))
    finally:
        for client in clients:
            subprocess.run(["docker", "rm", "-f", client], capture_output=True, check=False)


if __name__ == "__main__":
    main()
