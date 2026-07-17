"""Phase-1 integration probe: exercise the ambiance API in Mock/dry. Not shipped."""
import json
import urllib.error
import urllib.request

B = "http://127.0.0.1:8899"


def req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(B + path, data=data, method=method,
                               headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=6) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return None, str(e).encode()


def zone(b, zid):
    return [z for z in json.loads(b)["zones"] if z["id"] == zid][0]


c, b = req("GET", "/api/status")
d = json.loads(b)
print("1) status: zones=%d master_vol=%d master_mute=%s siren=%s radio_station=%s"
      % (len(d["zones"]), d["master_vol"], d["master_mute"], d["siren"], d["radio"]["station"]))

c, b = req("GET", "/api/stations")
print("2) stations: %d" % len(json.loads(b)["stations"]))

c, b = req("PATCH", "/api/zones/2", {"vol": 55})
print("3) zone2 vol -> %d" % zone(b, 2)["vol"])

req("PATCH", "/api/zones/2", {"power": False})
req("PATCH", "/api/zones/2", {"mute": True})
c, b = req("PATCH", "/api/zones/2", {"power": True})
z = zone(b, 2)
print("4) power/mute indep: mute=%s power=%s  (mute must stay True)" % (z["mute"], z["power"]))

c, b = req("PATCH", "/api/zones", {"vol": 40})
print("5) master vol 40 -> master_vol=%d zonevols=%s"
      % (json.loads(b)["master_vol"], [z["vol"] for z in json.loads(b)["zones"]]))

c, b = req("POST", "/api/announce", {"url": "http://192.168.1.181:8080/static/alarm.mp3"})
print("6) announce(dry): %s %s" % (c, b.decode()[:60]))

c, b = req("POST", "/api/alarm", {"on": True})
print("7) alarm on -> siren=%s" % json.loads(b)["siren"])
c, b = req("GET", "/api/alarm/selftest")
print("   selftest: %s" % b.decode()[:90])
c, b = req("POST", "/api/alarm", {"on": False})
print("   alarm off -> siren=%s" % json.loads(b)["siren"])

c, b = req("GET", "/api/cover")
print("8) cover HTTP %s" % c)
c, b = req("GET", "/openapi.json")
print("9) openapi.json HTTP %s (binding DTO source)" % c)
