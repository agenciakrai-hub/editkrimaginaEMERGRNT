import ast
import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timezone

ROOT = Path(__file__).parent / 'backend'

def extracted(file, names):
    tree = ast.parse((ROOT / file).read_text())
    return compile(ast.Module(body=[n for n in tree.body if getattr(n, 'name', '') in names], type_ignores=[]), file, 'exec')

scope = {}
exec(extracted('providers.py', {'ProviderRequestError', '_check_edit_response'}), scope)
Error = scope['ProviderRequestError']

class Response:
    def __init__(self, status, payload):
        self.status_code, self.payload = status, payload
    def json(self):
        if isinstance(self.payload, str):
            raise ValueError('HTML')
        return self.payload

class Collection:
    def __init__(self):
        self.updates = []
    async def find_one(self, query, *args):
        return {'id': query['id']}
    async def update_one(self, query, update):
        self.updates.append(update)

class Tests(unittest.TestCase):
    def test_provider_statuses(self):
        for status, code in [(429, 'rate_limited'), (504, 'provider_timeout'), (524, 'provider_timeout'), (520, 'provider_unavailable'), (401, 'provider_auth')]:
            with self.subTest(status=status), self.assertRaises(Error) as raised:
                scope['_check_edit_response'](Response(status, '<html>secret-token</html>'))
            self.assertEqual(raised.exception.code, code)
            self.assertNotIn('secret-token', str(raised.exception))

    def test_structured_quota(self):
        with self.assertRaises(Error) as raised:
            scope['_check_edit_response'](Response(502, {'error': {'code': 'rate_limited'}}))
        self.assertEqual(raised.exception.status_code, 429)

    def test_success(self):
        scope['_check_edit_response'](Response(200, {'ok': True}))

    def test_batch_stops_and_refunds_remaining(self):
        db = SimpleNamespace(photos=Collection(), jobs=Collection(), users=Collection())
        env = {'List': list, 'Optional': object, 'db': db, 'datetime': datetime, 'timezone': timezone,
               'logger': SimpleNamespace(exception=lambda *args: None)}
        exec(extracted('server.py', {'ProviderEditError', '_process_batch'}), env)
        calls = []
        async def edit(photo, *args):
            calls.append(photo['id'])
            if photo['id'] == 'b':
                raise env['ProviderEditError']('KRAI', 'gemini-image', 'Límite agotado', 'rate_limited', 429)
        env['_apply_edit'] = edit
        asyncio.run(env['_process_batch']('job', 'user', ['a', 'b', 'c', 'd'], 'pro', {}, None, 2))
        self.assertEqual(calls, ['a', 'b'])
        self.assertEqual(db.users.updates, [{'$inc': {'credits': 6}}])
        failure = next(u for u in db.jobs.updates if u.get('$set', {}).get('error_code'))
        self.assertEqual(failure['$inc'], {'failed': 3, 'processed': 3})
        self.assertEqual(failure['$set']['skipped'], 2)
        self.assertEqual(db.jobs.updates[-1]['$set']['status'], 'done')

if __name__ == '__main__':
    unittest.main()
