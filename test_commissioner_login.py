from app import app

with app.test_client() as client:
    # Log in as commissioner (seeded account: jay2006 / 123456)
    resp = client.post('/official-login', json={'role': 'commissioner', 'emp_id': 'jay2006', 'password': '123456'})
    print('Login status', resp.status_code, resp.json)
    if resp.status_code == 200 and resp.json.get('success'):
        # Call commissioner stats
        resp2 = client.get('/api/commissioner/stats')
        print('Stats status', resp2.status_code)
        print(resp2.json)
    else:
        print('Login failed, cannot query stats')
