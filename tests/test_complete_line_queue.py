import json

import pytest

def test_all_line_platforms_can_be_attempted_and_restart_skips_cache(tmp_path):
    from data_science.complete_lines import run_batches
    from data_science.ingest_stop_lines import IngestionError
    from data_science.stop_lines import read_cache
    platforms=[(f'{i:04}', '01') for i in range(123)]
    calls=[]
    def fetch(*key):
        calls.append(key)
        if key[0]=='0002':raise IngestionError('HTTP_404')
        if key[0]=='0003':raise IngestionError('TIMEOUT')
        return [] if key[0]=='0001' else ['001']
    path=tmp_path/'lines.csv'
    report=run_batches(platforms,path,fetch,max_batches=10,progress_path=tmp_path/'progress.json')
    assert len(calls)==123 and report['attempted_platforms']==123
    assert report['states']=={'known_with_lines':120,'known_empty':1,'permanent_error':1,'transient_error':1}
    assert read_cache(path).records[('0000','01')]['lines']==['001']
    run_batches(platforms,path,lambda *key:pytest.fail('Already attempted'),max_batches=10)
    retry=[]
    report=run_batches(platforms,path,lambda *key:retry.append(key) or [],max_batches=10,retry_errors=True)
    assert retry==[('0003','01')]
    assert report['states']['permanent_error']==1 and report['states']['known_empty']==2
    assert json.loads((tmp_path/'progress.json').read_text())['attempted_platforms']==123


def test_http_budget_stops_without_false_platform_observation(tmp_path):
    import httpx
    from data_science.complete_lines import run_batches
    from data_science.ingest_stop_lines import LineClient
    from data_science.stop_lines import read_cache
    calls=[]
    def unavailable(request):calls.append(request);return httpx.Response(503)
    with httpx.Client(transport=httpx.MockTransport(unavailable)) as http:
        client=LineClient(http,'example-only',max_requests=2,sleep=lambda _:None)
        report=run_batches([('0001','01'),('0002','01')],tmp_path/'lines.csv',client.fetch,max_batches=5)
    assert len(calls)==client.requests==2
    assert report['attempted_platforms']==1
    assert read_cache(tmp_path/'lines.csv').records[('0001','01')]['error_code']=='HTTP_503'
    assert ('0002','01') not in read_cache(tmp_path/'lines.csv').records


def test_multi_batch_requires_verified_policy_before_http(tmp_path,monkeypatch):
    from data_science.complete_lines import main,verified_policy
    monkeypatch.delenv('WARSAW_API_TOKEN',raising=False)
    with pytest.raises(SystemExit):main(['--max-batches','2','--output',str(tmp_path/'lines.csv')])
    assert not (tmp_path/'lines.csv').exists()
    policy=tmp_path/'policy.json';policy.write_text(json.dumps({'official_policy_url':'https://unofficial.invalid/limits'}))
    with pytest.raises(ValueError):verified_policy(policy)


def test_line_response_body_is_bounded():
    import httpx
    from data_science.ingest_stop_lines import LineClient,IngestionError
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,content=b' '*256001))) as http:
        with pytest.raises(IngestionError,match='RESPONSE_TOO_LARGE'):
            LineClient(http,'example-only',sleep=lambda _:None).fetch('0001','01')

