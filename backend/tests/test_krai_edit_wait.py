import ast, base64, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

class ProviderRequestError(Exception):
    def __init__(self,code,status_code,message): self.code=code; self.status_code=status_code;super().__init__(message)
class Timeout(Exception): pass
source=ast.parse(Path(__file__).resolve().parents[1].joinpath('providers.py').read_text())
nodes=[n for n in source.body if isinstance(n,ast.FunctionDef) and n.name in {'_krai_edit','_check_edit_response'}]
ns={'ProviderRequestError':ProviderRequestError,'image_mime':lambda b:'image/png','logger':SimpleNamespace(warning=lambda *a:None)}
exec(compile(ast.Module(body=nodes,type_ignores=[]),'krai-edit','exec'),ns)
def response(code):
    return SimpleNamespace(status_code=code,json=lambda:{'ok':True,'artifacts':[{'type':'image','mime_type':'image/png','data_b64':base64.b64encode(b'edited').decode()}]})
class WaitTests(unittest.TestCase):
    def test_transport_wait_covers_chatgpt_deadline(self):
        calls=[]
        def post(*a,**k):calls.append(k);return response(200)
        ns['requests']=SimpleNamespace(post=post,Timeout=Timeout)
        self.assertEqual(ns['_krai_edit']('https://example.invalid','redacted','chatgpt',b'input','light'),b'edited')
        self.assertGreater(calls[0]['timeout'][1],115);self.assertEqual(calls[0]['json']['options']['timeout_ms'],110000)
    def test_busy_wait_is_bounded_and_uses_same_request_id(self):
        calls=[]
        def post(*a,**k):calls.append(k);return response(409 if len(calls)<3 else 200)
        ns['requests']=SimpleNamespace(post=post,Timeout=Timeout)
        with patch('time.sleep') as sleep: ns['_krai_edit']('https://example.invalid','redacted','chatgpt',b'input','light')
        self.assertEqual(len(calls),3);self.assertEqual(sleep.call_count,2);self.assertEqual(len({x['json']['client_request_id'] for x in calls}),1)
    def test_saturated_provider_is_not_polled_forever(self):
        calls=[]
        def post(*a,**k): calls.append(k);return response(409)
        ns['requests']=SimpleNamespace(post=post,Timeout=Timeout)
        with patch('time.sleep'), self.assertRaises(ProviderRequestError) as e:ns['_krai_edit']('https://example.invalid','redacted','chatgpt',b'input','light')
        self.assertEqual(len(calls),7);self.assertEqual(e.exception.code,'provider_busy')
    def test_generation_timeout_never_resubmitted(self):
        calls=[]
        def post(*a,**k):calls.append(k);return response(504)
        ns['requests']=SimpleNamespace(post=post,Timeout=Timeout)
        with self.assertRaises(ProviderRequestError):ns['_krai_edit']('https://example.invalid','redacted','chatgpt',b'input','light')
        self.assertEqual(len(calls),1)
    def test_connection_timeout_never_resubmitted(self):
        calls=[]
        def post(*a,**k):calls.append(k);raise Timeout()
        ns['requests']=SimpleNamespace(post=post,Timeout=Timeout)
        with self.assertRaises(ProviderRequestError):ns['_krai_edit']('https://example.invalid','redacted','chatgpt',b'input','light')
        self.assertEqual(len(calls),1)
if __name__=='__main__': unittest.main()
