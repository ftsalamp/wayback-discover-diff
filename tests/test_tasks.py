from wayback_discover_diff import Discover
from flask import json
import os
import yaml
from celery import Celery

with open(os.environ['WAYBACK_DISCOVER_DIFF_CONF'], 'r') as ymlfile:
    CFG = yaml.load(ymlfile)

APP = Discover(CFG)

# Initialize Celery and register Discover task.
celery = Celery(__name__, broker=CFG['celery_broker'], backend=CFG['celery_backend'])
celery.register_task(APP)


def test_no_url():
    url = None
    timestamp = '20141115130953'
    result = APP.timestamp_simhash(url, timestamp)
    assert json.dumps({'error': 'URL is required.'}) == result


def test_no_timestamp():
    url = 'iskme.org'
    timestamp = None
    result = APP.timestamp_simhash(url, timestamp)
    assert json.dumps({'error': 'Timestamp is required.'}) == result


def test_no_entry():
    url = 'nonexistingdomain.org'
    timestamp = '20180000000000'
    result = APP.timestamp_simhash(url, timestamp)
    assert json.dumps({'simhash': 'None'}) == result


# def test_start_task():
#     url = 'iskme.org'
#     year = '2018'
#     job_id = celery.tasks['Discover'].apply(args=[url, year])
#     assert job_id is not None


def test_task_no_url():
    url = None
    year = '2018'
    job = celery.tasks['Discover'].apply(args=[url, year])
    assert job.get() == json.dumps({'status':'error', 'info': 'URL is required.'})


def test_task_no_year():
    url = 'nonexistingdomain.org'
    year = None
    job = celery.tasks['Discover'].apply(args=[url, year])
    assert job.get() == json.dumps({'status':'error', 'info': 'Year is required.'})


def test_task_no_snapshots():
    url = 'nonexistingdomain.org'
    year = '2018'
    job = celery.tasks['Discover'].apply(args=[url, year])
    assert job.get() == json.dumps({'status':'error', 'info': 'no snapshots found for this year and url combination'})


def test_success_calc_simhash():
    url = 'iskme.org'
    year = '2018'
    job = celery.tasks['Discover'].apply(args=[url, year])
    task_info = json.loads(job.info)
    assert task_info.get('duration', -1) != -1
