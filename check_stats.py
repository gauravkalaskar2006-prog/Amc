import urllib.request
from urllib.error import HTTPError

req = urllib.request.Request('http://127.0.0.1:5000/api/commissioner/stats')
req.add_header('Cookie', 'session=eyXo...')

try:
    resp = urllib.request.urlopen(req)
    print(resp.read().decode())
except HTTPError as e:
    print(f"Error {e.code}:")
    print(e.read().decode())
except Exception as e:
    print("Other error:", str(e))
