"""Read retained synthetic evidence; never promotes a worker, PR or deployment.

Usage: python3 evaluate_run.py /path/to/qualification tuple.json indexed-soak.json default-http.json indexed-http.json
"""
import json
from pathlib import Path
import sys


def main():
    qualification, pins, stream, http_unindexed, http_indexed = map(Path, sys.argv[1:])
    load = lambda p: json.loads(p.read_bytes())
    suite = load(qualification/'summary.json'); pins, bench, default, indexed = map(load, (pins, stream, http_unindexed, http_indexed))
    assert all(x['tuple'] == pins for x in (suite, bench, default, indexed)), 'mixed evidence tuples'
    assert suite['passed'] is True and set(suite['junit']) == {'workflow','hyvv','bundlebees','orbitdesktop','orbit-node'}
    for x in suite['junit'].values():
        assert x['tests'] > 0 and all(x[k] == 0 for k in ('errors','skipped','failures'))
    assert bench['status'] == default['status'] == indexed['status'] == 'completed'
    conf = bench['config']; stream = bench['stream']; clock = stream['elapsed_s']
    assert (conf['events'],conf['samples_per_surface'],conf['soak_seconds'],conf['lanes'],conf['attempt_index']) == (100_000,100,1800,10,True)
    assert bench['seed']['unique_seed_ids'] == 100_000 and len(set(bench['seed']['writer_pids'])) == 10
    assert len(stream['cycles']) == 180 and [x['cycles'] for x in stream['windows']] == [30]*6 and clock >= 1800
    assert stream['browser']['dom_marks'] == 2000 and stream['browser']['input_marks'] == 2500
    assert default['indexed_before_seed'] is False and indexed['indexed_before_seed'] is True
    checks = {}
    for surface, d in [('http_default',default),('http_indexed',indexed)]:
        assert d['seed']['unique_seed_ids'] == 100_000
        for kind in ('events','view'):
            samples = d['series'][kind]; assert len(samples) == 100
            observed = sorted(s['logical_ms'] for s in samples)[94]
            assert observed == d[kind+'_p95_ms']
            checks[surface+'_'+kind] = {'p95_ms':observed, 'limit_ms':500, 'pass':observed <= 500}
    for kind, d in bench['reads']['series'].items():
        observed = d['p95_logical_500_ms']
        checks['retained_'+kind] = {'p95_ms':observed,'limit_ms':500,'pass':observed <= 500}
    vis = stream['p95_connected']['browser_visible_ms']
    checks['connected_visible'] = {'p95_ms':vis,'limit_ms':3000,'pass':vis <= 3000}
    print(json.dumps(dict(tuple=pins, junit_tests=sum(v['tests'] for v in suite['junit'].values()), skips=0,
                          soak_seconds=clock, windows=stream['windows'], latency=checks,
                          memory='descriptive: review six windows and process trends; no numeric leak bound was frozen',
                          scope='synthetic Linux; separate 2000-mark cap test and connected viewport; physical SSD unknown'),indent=2))


if __name__ == '__main__':
    main()
