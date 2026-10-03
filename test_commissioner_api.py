import urllib.request, json

url = 'http://127.0.0.1:5000/api/commissioner/stats'
try:
    with urllib.request.urlopen(url, timeout=5) as r:
        print('Status:', r.status)
        print(r.read().decode())
except Exception as e:
    print('Error:', e)
