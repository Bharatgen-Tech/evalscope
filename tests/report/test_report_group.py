# Copyright (c) Alibaba, Inc. and its affiliates.
"""Unit tests for the background group job (POST /api/v1/reports/group +
GET /api/v1/reports/group/status).

The job runs in a real background thread, so tests poll `get_group_job_status`
(or the HTTP status endpoint) until it settles, with a bounded timeout instead
of a fixed sleep.

Skipped automatically when Flask (service extra) is not installed.
"""
import json
import os
import pytest
import shutil
import tempfile
import time
import unittest
from unittest import mock

flask = pytest.importorskip('flask')  # noqa: F841  (service extra not installed → skip)

from evalscope.service import grouping  # noqa: E402


def _report_dict(model_name: str, dataset_name: str, num: int = 10, score: float = 0.5) -> dict:
    return {
        'name': f'{model_name}@{dataset_name}',
        'dataset_name': dataset_name,
        'model_name': model_name,
        'score': score,
        'metrics': [{
            'name': 'acc',
            'categories': [{
                'name': ['default'],
                'subsets': [{
                    'name': 'default',
                    'score': score,
                    'num': num,
                }],
            }],
        }],
    }


def _write_json(path: str, obj: object) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f)


def _write_run(run_dir: str, model: str, datasets: list, score: float = 0.5) -> None:
    for dataset in datasets:
        _write_json(os.path.join(run_dir, 'reports', model, f'{dataset}.json'), _report_dict(model, dataset, score=score))
        _write_json(os.path.join(run_dir, 'predictions', model, f'{dataset}_default.jsonl'), {})
        _write_json(os.path.join(run_dir, 'reviews', model, f'{dataset}_default.jsonl'), {})
    os.makedirs(os.path.join(run_dir, 'logs'), exist_ok=True)
    configs_dir = os.path.join(run_dir, 'configs')
    os.makedirs(configs_dir, exist_ok=True)
    import yaml
    with open(os.path.join(configs_dir, 'task_config.yaml'), 'w', encoding='utf-8') as f:
        yaml.safe_dump({'model': model, 'datasets': datasets}, f)


def _wait_until(predicate, timeout=10.0, interval=0.05):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


class TestReportGroup(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        # Reset the module-level job registry so tests don't leak into each other.
        grouping._jobs.clear()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        grouping._jobs.clear()

    def test_status_is_idle_before_anything_runs(self):
        self.assertEqual(grouping.get_group_job_status(self.tmp), {'status': 'idle'})
        self.assertFalse(grouping.is_group_job_running(self.tmp))

    def test_groups_same_model_reports_across_the_whole_root(self):
        _write_run(os.path.join(self.tmp, '20260101_120000'), 'model-a', ['gsm8k'])
        _write_run(os.path.join(self.tmp, '20260102_120000'), 'model-a', ['mmlu'])
        _write_run(os.path.join(self.tmp, '20260103_120000'), 'model-a', ['arc'])

        grouping.start_group_job(self.tmp)
        _wait_until(lambda: grouping.get_group_job_status(self.tmp).get('status') != 'running')

        status = grouping.get_group_job_status(self.tmp)
        self.assertEqual(status['status'], 'completed')
        self.assertEqual(status['groups_total'], 1)
        self.assertEqual(len(status['result']), 1)
        self.assertTrue(status['result'][0]['success'])

        grouped_prefix = status['result'][0]['report_name'].split('@@')[0]
        grouped_reports_dir = os.path.join(self.tmp, grouped_prefix, 'reports', 'model-a')
        self.assertEqual(
            sorted(f for f in os.listdir(grouped_reports_dir) if f.endswith('.json')),
            ['arc.json', 'gsm8k.json', 'mmlu.json'],
        )

        # Originals are archived, not deleted, and no longer show up in a scan.
        for prefix in ('20260101_120000', '20260102_120000', '20260103_120000'):
            self.assertFalse(os.path.isdir(os.path.join(self.tmp, prefix)))
            self.assertTrue(os.path.isdir(os.path.join(self.tmp, '.archived', prefix, 'reports', 'model-a')))

        scanned = grouping.scan_for_report_folders(self.tmp)
        self.assertEqual(len(scanned), 1)
        self.assertTrue(scanned[0].startswith(f'{grouped_prefix}@@model-a::'))

    def test_prefers_the_most_recent_source_on_dataset_overlap(self):
        _write_run(os.path.join(self.tmp, '20260101_120000'), 'model-a', ['gsm8k'], score=0.1)
        _write_run(os.path.join(self.tmp, '20260102_120000'), 'model-a', ['gsm8k', 'mmlu'], score=0.9)

        grouping.start_group_job(self.tmp)
        _wait_until(lambda: grouping.get_group_job_status(self.tmp).get('status') != 'running')

        status = grouping.get_group_job_status(self.tmp)
        self.assertEqual(status['status'], 'completed')
        grouped_prefix = status['result'][0]['report_name'].split('@@')[0]
        gsm8k_path = os.path.join(self.tmp, grouped_prefix, 'reports', 'model-a', 'gsm8k.json')
        with open(gsm8k_path, 'r', encoding='utf-8') as f:
            self.assertEqual(json.load(f)['score'], 0.9)  # the later (20260102) source wins

    def test_skips_models_with_only_one_report(self):
        _write_run(os.path.join(self.tmp, '20260101_120000'), 'model-a', ['gsm8k'])
        _write_run(os.path.join(self.tmp, '20260102_120000'), 'model-a', ['mmlu'])
        _write_run(os.path.join(self.tmp, '20260103_120000'), 'model-b', ['arc'])

        grouping.start_group_job(self.tmp)
        _wait_until(lambda: grouping.get_group_job_status(self.tmp).get('status') != 'running')

        status = grouping.get_group_job_status(self.tmp)
        self.assertEqual(status['groups_total'], 1)  # only model-a (2 reports); model-b (1) is skipped
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, '20260103_120000')))  # model-b left untouched

    def test_skips_reports_belonging_to_a_running_task(self):
        _write_run(os.path.join(self.tmp, '20260101_120000'), 'model-a', ['gsm8k'])
        _write_run(os.path.join(self.tmp, '20260102_120000'), 'model-a', ['mmlu'])

        with mock.patch('evalscope.service.grouping.active_task_ids', return_value={'20260101_120000'}):
            grouping.start_group_job(self.tmp)
            _wait_until(lambda: grouping.get_group_job_status(self.tmp).get('status') != 'running')

        status = grouping.get_group_job_status(self.tmp)
        self.assertEqual(status['groups_total'], 0)  # only 1 non-running report for model-a: nothing to group
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, '20260101_120000')))  # untouched, still "running"

    def test_rejects_starting_a_second_job_while_one_is_running(self):
        import threading
        started = threading.Event()
        release = threading.Event()

        def blocking_group_one_model(root, model_name, items):
            started.set()
            release.wait(timeout=5)
            raise ValueError('cancelled for test')

        _write_run(os.path.join(self.tmp, '20260101_120000'), 'model-a', ['gsm8k'])
        _write_run(os.path.join(self.tmp, '20260102_120000'), 'model-a', ['mmlu'])

        with mock.patch('evalscope.service.grouping._group_one_model', side_effect=blocking_group_one_model):
            grouping.start_group_job(self.tmp)
            self.assertTrue(started.wait(timeout=5))
            self.assertTrue(grouping.is_group_job_running(self.tmp))
            with self.assertRaises(ValueError):
                grouping.start_group_job(self.tmp)
            release.set()
            _wait_until(lambda: grouping.get_group_job_status(self.tmp).get('status') != 'running')


class TestReportGroupEndpoints(unittest.TestCase):
    """Exercises the same behaviour through the Flask HTTP layer."""

    def setUp(self):
        from evalscope.service.app import create_app

        self.tmp = tempfile.mkdtemp()
        grouping._jobs.clear()
        self.client = create_app().test_client()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        grouping._jobs.clear()

    def test_start_returns_202_then_status_reaches_completed(self):
        _write_run(os.path.join(self.tmp, '20260101_120000'), 'model-a', ['gsm8k'])
        _write_run(os.path.join(self.tmp, '20260102_120000'), 'model-a', ['mmlu'])

        res = self.client.post('/api/v1/reports/group', json={'root_path': self.tmp})
        self.assertEqual(res.status_code, 202)
        self.assertEqual(res.get_json()['status'], 'started')

        def is_done():
            status_res = self.client.get('/api/v1/reports/group/status', query_string={'root_path': self.tmp})
            return status_res.get_json().get('status') != 'running'

        self.assertTrue(_wait_until(is_done))
        final = self.client.get('/api/v1/reports/group/status', query_string={'root_path': self.tmp}).get_json()
        self.assertEqual(final['status'], 'completed')

    def test_start_rejects_second_job_with_409(self):
        _write_run(os.path.join(self.tmp, '20260101_120000'), 'model-a', ['gsm8k'])
        _write_run(os.path.join(self.tmp, '20260102_120000'), 'model-a', ['mmlu'])

        import threading
        started = threading.Event()
        release = threading.Event()

        def blocking_group_one_model(root, model_name, items):
            started.set()
            release.wait(timeout=5)
            raise ValueError('cancelled for test')

        with mock.patch('evalscope.service.grouping._group_one_model', side_effect=blocking_group_one_model):
            first = self.client.post('/api/v1/reports/group', json={'root_path': self.tmp})
            self.assertEqual(first.status_code, 202)
            self.assertTrue(started.wait(timeout=5))

            second = self.client.post('/api/v1/reports/group', json={'root_path': self.tmp})
            self.assertEqual(second.status_code, 409)

            release.set()
            self.assertTrue(_wait_until(lambda: not grouping.is_group_job_running(self.tmp)))

    def test_merge_delete_rename_reject_while_group_job_running(self):
        _write_run(os.path.join(self.tmp, '20260101_120000'), 'model-a', ['gsm8k'])
        _write_run(os.path.join(self.tmp, '20260102_120000'), 'model-a', ['mmlu'])

        import threading
        started = threading.Event()
        release = threading.Event()

        def blocking_group_one_model(root, model_name, items):
            started.set()
            release.wait(timeout=5)
            raise ValueError('cancelled for test')

        with mock.patch('evalscope.service.grouping._group_one_model', side_effect=blocking_group_one_model):
            self.client.post('/api/v1/reports/group', json={'root_path': self.tmp})
            self.assertTrue(started.wait(timeout=5))

            delete_res = self.client.delete(
                '/api/v1/reports/report',
                query_string={'root_path': self.tmp, 'report_name': '20260101_120000@@model-a::gsm8k'},
            )
            self.assertEqual(delete_res.status_code, 409)

            merge_res = self.client.post(
                '/api/v1/reports/merge',
                json={
                    'root_path': self.tmp,
                    'report_names': ['20260101_120000@@model-a::gsm8k', '20260102_120000@@model-a::mmlu'],
                },
            )
            self.assertEqual(merge_res.status_code, 409)

            rename_res = self.client.post(
                '/api/v1/reports/rename',
                json={
                    'root_path': self.tmp,
                    'report_name': '20260101_120000@@model-a::gsm8k',
                    'new_model_name': 'model-a-v2',
                },
            )
            self.assertEqual(rename_res.status_code, 409)

            release.set()
            self.assertTrue(_wait_until(lambda: not grouping.is_group_job_running(self.tmp)))


if __name__ == '__main__':
    unittest.main()
