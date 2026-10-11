import asyncio
import unittest
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from work_heartbeat import stale_work_filter, run_with_heartbeat, batch_public

class RecoveryTests(unittest.TestCase):
    def matches(self, doc, query):
        for clause in query['$or']:
            ok = True
            for key, conditions in clause.items():
                for op, value in conditions.items():
                    if op == '$exists': ok &= (key in doc) == value
                    if op == '$lt': ok &= key in doc and doc[key] < value
            if ok: return True
        return False
    def test_live_long_batch_is_not_stale(self):
        now = datetime.now(timezone.utc)
        self.assertFalse(self.matches({'created_at':(now-timedelta(hours=2)).isoformat(), 'heartbeat_at':now.isoformat()}, stale_work_filter(now)))
    def test_expired_lease_is_stale(self):
        now = datetime.now(timezone.utc)
        self.assertTrue(self.matches({'heartbeat_at':(now-timedelta(minutes=21)).isoformat()}, stale_work_filter(now)))
    def test_legacy_grace_period(self):
        now=datetime.now(timezone.utc)
        for minutes, expected in [(1,False),(21,True)]:
            self.assertEqual(self.matches({'created_at':(now-timedelta(minutes=minutes)).isoformat()},stale_work_filter(now)),expected)
    def test_completed_batch_no_false_interruption(self):
        original={'status':'interrupted','total':38,'processed':38,'done':27,'failed':11,'error_message':'El lote se interrumpió antes de completar todas las fotos.'}
        result=batch_public(original)
        self.assertEqual(result['status'],'done')
        self.assertIn('11 fotos',result['error_message'])
        self.assertEqual(original['status'],'interrupted')
    def test_incomplete_batch_keeps_interruption(self):
        job={'status':'interrupted','total':38,'processed':35}
        self.assertEqual(batch_public(job),job)

class HeartbeatTests(unittest.IsolatedAsyncioTestCase):
    async def test_heartbeat_stops_after_success(self):
        calls=[]
        async def update(query, data): calls.append((query,data))
        db=SimpleNamespace(jobs=SimpleNamespace(update_one=update))
        async def work():
            await asyncio.sleep(.035)
            return 'saved'
        self.assertEqual(await run_with_heartbeat(db,'j',work,interval=.01),'saved')
        count=len(calls); self.assertGreaterEqual(count,2)
        await asyncio.sleep(.02); self.assertEqual(len(calls),count)
        self.assertEqual(calls[0][0]['status']['$in'],['starting','processing'])
    async def test_heartbeat_stops_after_failure(self):
        calls=[]
        async def update(query,data): calls.append(data)
        db=SimpleNamespace(jobs=SimpleNamespace(update_one=update))
        async def work():
            await asyncio.sleep(.015)
            raise ValueError('provider failure')
        with self.assertRaisesRegex(ValueError,'provider failure'):
            await run_with_heartbeat(db,'j',work,interval=.005)
        count=len(calls)
        await asyncio.sleep(.02); self.assertEqual(len(calls),count)
