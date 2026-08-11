"""Background "group same-model reports" job.

Runs as a plain Python thread inside the Flask process, not a subprocess -
this is pure file I/O (moving/copying report directories) with no GPU or
model work, so subprocess isolation would only add multiprocessing-spawn
overhead for no benefit. See ``evalscope.service.blueprints.reports``'s
``/merge`` and ``/rename`` endpoints for the synchronous, single-selection
equivalent this reuses and extends to the whole output directory.

Progress is tracked purely in memory, keyed by the realpath'd root
directory being processed - simpler than the file-based ``progress.json``
scheme eval/perf tasks use, which exists only because those run in a
separate OS process and need to communicate across that boundary. At most
one group job runs per root at a time.
"""
import glob
import json
import os
import shutil
import threading
import uuid
from datetime import datetime
from typing import Any, Dict, List, Tuple

from evalscope.report.report import Report
from evalscope.utils.data_utils import process_report_name, scan_for_report_folders
from evalscope.utils.io_utils import OutputsStructure, dict_to_yaml, yaml_to_dict
from evalscope.utils.logger import get_logger
from .utils import active_task_ids

logger = get_logger()

_jobs: Dict[str, Dict[str, Any]] = {}
_jobs_lock = threading.Lock()


def _job_key(root: str) -> str:
    return os.path.realpath(root)


def is_group_job_running(root: str) -> bool:
    """Whether a group job is currently running for this root."""
    with _jobs_lock:
        job = _jobs.get(_job_key(root))
        return bool(job) and job.get('status') == 'running'


def get_group_job_status(root: str) -> Dict[str, Any]:
    """Return the status of the most recent group job for this root.

    ``{'status': 'idle'}`` when no group job has ever run for this root.
    """
    with _jobs_lock:
        job = _jobs.get(_job_key(root))
        return dict(job) if job is not None else {'status': 'idle'}


def _update_job(root: str, **fields: Any) -> None:
    with _jobs_lock:
        job = _jobs.setdefault(_job_key(root), {})
        job.update(fields)
        job['updated_at'] = datetime.now().isoformat()


def start_group_job(root: str) -> None:
    """Start a background job that groups same-model reports under `root`.

    Raises:
        ValueError: if a group job is already running for this root.
    """
    if is_group_job_running(root):
        raise ValueError('A group job is already running for this directory')

    _update_job(
        root,
        status='running',
        percent=0.0,
        groups_total=0,
        groups_done=0,
        error=None,
        result=None,
        started_at=datetime.now().isoformat(),
    )
    threading.Thread(target=_run_group_job, args=(root, ), daemon=False).start()


def _run_group_job(root: str) -> None:
    try:
        raw_reports = scan_for_report_folders(root)
        running = active_task_ids()

        by_model: Dict[str, List[Tuple[str, str]]] = {}
        for name in raw_reports:
            try:
                prefix, model_name, _ = process_report_name(name)
            except ValueError:
                continue
            if prefix in running:
                # Skip reports belonging to a still-executing eval/perf task.
                continue
            by_model.setdefault(model_name, []).append((name, prefix))

        # Nothing to do for a model with only one report.
        groups = {model: items for model, items in by_model.items() if len(items) >= 2}
        _update_job(root, groups_total=len(groups))

        results = []
        for i, (model_name, items) in enumerate(groups.items()):
            try:
                merged_name = _group_one_model(root, model_name, items)
                results.append({'model_name': model_name, 'report_name': merged_name, 'success': True})
            except Exception as e:
                logger.error(f'Failed to group reports for model {model_name!r}: {e}')
                results.append({'model_name': model_name, 'success': False, 'error': str(e)})
            _update_job(
                root,
                groups_done=i + 1,
                percent=round((i + 1) / len(groups) * 100, 1) if groups else 100.0,
            )

        _update_job(root, status='completed', result=results)
    except Exception as e:
        logger.error(f'Group job failed for root {root}: {e}')
        _update_job(root, status='error', error=str(e))


def _group_one_model(root: str, model_name: str, items: List[Tuple[str, str]]) -> str:
    """Merge every report belonging to `model_name` under `root`, preferring
    the most recently-run source when the same dataset appears in more than
    one, then archive the original sources.

    Returns:
        str: the identifier of the newly created grouped report.
    """
    # Deferred import: breaks the circular dependency (reports.py imports
    # this module's public job functions at top level; these internals need
    # a few of reports.py's private helpers, but only once a job actually
    # runs, long after both modules have finished loading).
    from evalscope.constants import DATASET_TOKEN, MODEL_TOKEN, REPORT_TOKEN
    from evalscope.service.blueprints.reports import (
        DataCollection,
        _extract_timestamp,
        _refresh_html_report,
        _resolve_run_dir,
    )

    root_real = os.path.realpath(root)

    # For each dataset json filename, keep only the most recently-run source
    # that has it.
    dataset_source: Dict[str, Tuple[str, str, str]] = {}  # json_name -> (timestamp, prefix, model_report_dir)
    source_dirs: List[Tuple[str, str, str, str]] = []  # (name, prefix, run_dir, model_report_dir)
    for name, prefix in items:
        try:
            run_dir = _resolve_run_dir(root, prefix)
        except ValueError:
            continue
        model_report_dir = os.path.join(run_dir, OutputsStructure.REPORTS_DIR, model_name)
        if not os.path.isdir(model_report_dir):
            continue
        timestamp = _extract_timestamp(name, root)
        source_dirs.append((name, prefix, run_dir, model_report_dir))
        for json_name in os.listdir(model_report_dir):
            if not json_name.endswith('.json') or json_name == DataCollection.REPORT_NAME:
                continue
            current = dataset_source.get(json_name)
            if current is None or timestamp > current[0]:
                dataset_source[json_name] = (timestamp, prefix, model_report_dir)

    if len(source_dirs) < 2 or not dataset_source:
        raise ValueError(f'Nothing to group for model {model_name!r}')

    new_prefix = f'grouped_{datetime.now().strftime("%Y%m%d_%H%M%S")}_{uuid.uuid4().hex[:8]}'
    new_run_dir = os.path.join(root_real, new_prefix)

    try:
        new_reports_dir = os.path.join(new_run_dir, OutputsStructure.REPORTS_DIR, model_name)
        os.makedirs(new_reports_dir, exist_ok=True)

        merged_datasets = sorted(dataset_source.keys())
        for json_name, (_ts, _prefix, model_report_dir) in dataset_source.items():
            shutil.copy2(os.path.join(model_report_dir, json_name), os.path.join(new_reports_dir, json_name))

        # predictions/reviews: for each dataset, copy its subset files from
        # whichever source won that dataset (files are named
        # "{dataset}_{subset}.jsonl" or "{dataset}.jsonl").
        for sub in (OutputsStructure.PREDICTIONS_DIR, OutputsStructure.REVIEWS_DIR):
            for json_name, (_ts, prefix, _mrd) in dataset_source.items():
                dataset_stub = os.path.splitext(json_name)[0]
                src = os.path.join(root_real, prefix, sub, model_name)
                if not os.path.isdir(src):
                    continue
                dst = os.path.join(new_run_dir, sub, model_name)
                for entry in os.listdir(src):
                    if entry == f'{dataset_stub}.jsonl' or entry.startswith(f'{dataset_stub}_'):
                        os.makedirs(dst, exist_ok=True)
                        shutil.copy2(os.path.join(src, entry), os.path.join(dst, entry))

        # Merge configs: base on the most-recently-run source's config,
        # override datasets with the merged set.
        base_task_cfg = None
        merged_dataset_args: Dict[str, Any] = {}
        for _name, _prefix, run_dir, _mrd in sorted(source_dirs, key=lambda x: x[0]):
            config_files = sorted(glob.glob(os.path.join(run_dir, OutputsStructure.CONFIGS_DIR, '*.yaml')))
            if not config_files:
                continue
            task_cfg = yaml_to_dict(config_files[0])
            if isinstance(task_cfg, dict):
                base_task_cfg = dict(task_cfg)
                if isinstance(task_cfg.get('dataset_args'), dict):
                    merged_dataset_args.update(task_cfg['dataset_args'])

        if base_task_cfg is not None:
            base_task_cfg['datasets'] = merged_datasets
            if merged_dataset_args:
                base_task_cfg['dataset_args'] = merged_dataset_args
            dict_to_yaml(base_task_cfg, os.path.join(new_run_dir, OutputsStructure.CONFIGS_DIR, 'task_config.yaml'))

        total_num = 0
        for json_name in os.listdir(new_reports_dir):
            if not json_name.endswith('.json'):
                continue
            try:
                total_num += Report.from_json(os.path.join(new_reports_dir, json_name)).num
            except Exception:
                pass

        with open(os.path.join(new_run_dir, 'progress.json'), 'w', encoding='utf-8') as f:
            json.dump({
                'status': 'completed',
                'pipeline': 'eval',
                'total_count': total_num,
                'processed_count': total_num,
                'percent': 100.0,
                'updated_at': datetime.now().isoformat(),
            }, f)

        try:
            from evalscope.report import gen_html_report_file
            gen_html_report_file(os.path.join(new_run_dir, OutputsStructure.REPORTS_DIR))
        except Exception as e:
            logger.warning(f'Failed to generate HTML report for grouped run {new_prefix}: {e}')
    except Exception:
        shutil.rmtree(new_run_dir, ignore_errors=True)
        raise

    # Archive every source now that its data lives in the new grouped report.
    for _name, prefix, _run_dir, _mrd in source_dirs:
        _archive_model_report(root_real, prefix, model_name, _refresh_html_report)

    return f'{new_prefix}{REPORT_TOKEN}{model_name}{MODEL_TOKEN}{DATASET_TOKEN.join(merged_datasets)}'


def _archive_model_report(root: str, prefix: str, model_name: str, refresh_html_report) -> None:
    """Move a report's per-model artefacts into `<root>/.archived/`, mirroring
    the run's original layout, instead of deleting them outright.

    `<root>/.archived` sits outside the `<root>/*` glob `scan_for_report_folders`
    uses (a leading-dot directory is never matched by `glob.glob('*')`), so
    archived reports simply stop appearing in the reports list.
    """
    run_dir = os.path.join(root, prefix)
    archive_run_dir = os.path.join(root, '.archived', prefix)

    for sub in (OutputsStructure.REPORTS_DIR, OutputsStructure.PREDICTIONS_DIR, OutputsStructure.REVIEWS_DIR):
        src = os.path.join(run_dir, sub, model_name)
        if not os.path.isdir(src):
            continue
        dst = os.path.join(archive_run_dir, sub, model_name)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        shutil.move(src, dst)

    reports_dir = os.path.join(run_dir, OutputsStructure.REPORTS_DIR)
    has_reports = os.path.isdir(reports_dir) and any(
        os.path.isdir(os.path.join(reports_dir, name)) for name in os.listdir(reports_dir)
    )
    if not has_reports:
        # Last model report gone from this run dir: archive whatever's left
        # (logs/configs/progress.json/report.html) and drop the empty shell.
        # reports/predictions/reviews are skipped here - their real content
        # was already moved above; what's left of them are empty shells that
        # would otherwise collide with (and rmtree!) the archive dirs the
        # first loop just populated.
        already_archived = {
            OutputsStructure.REPORTS_DIR,
            OutputsStructure.PREDICTIONS_DIR,
            OutputsStructure.REVIEWS_DIR,
        }
        os.makedirs(archive_run_dir, exist_ok=True)
        if os.path.isdir(run_dir):
            for entry in os.listdir(run_dir):
                if entry in already_archived:
                    continue
                src = os.path.join(run_dir, entry)
                dst = os.path.join(archive_run_dir, entry)
                if os.path.exists(dst):
                    shutil.rmtree(dst) if os.path.isdir(dst) else os.remove(dst)
                shutil.move(src, dst)
            shutil.rmtree(run_dir, ignore_errors=True)
    else:
        try:
            refresh_html_report(reports_dir)
        except Exception:
            pass
