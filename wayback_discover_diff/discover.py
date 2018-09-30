import json
import concurrent.futures
import logging
import datetime
import cProfile
from math import ceil
import struct
import http.client
import base64
from itertools import groupby
import xxhash
from celery import Task
from urllib.parse import urlparse
import redis
from simhash import Simhash
from surt import surt
from lxml.html import fromstring, tostring
from lxml.html import html5parser
from lxml.html.clean import clean_html

class Discover(Task):
    """Custom Celery Task class.
    http://docs.celeryproject.org/en/latest/userguide/tasks.html#custom-task-classes
    """
    name = 'Discover'
    task_id = None

    def __init__(self, cfg):
        self.simhash_size = cfg['simhash']['size']
        self.simhash_expire = cfg['simhash']['expire_after']
        self.http = http.client.HTTPConnection("web.archive.org")
        redis_host = cfg['redis']['host']
        redis_port = cfg['redis']['port']
        redis_db = cfg['redis']['db']
        logfile = cfg['logfile']['name']
        loglevel = cfg['logfile']['level']
        self.thread_number = cfg['threads']
        self.snapshots_number = cfg['snapshots']['number_per_year']
        self.snapshots_per_page = cfg['snapshots']['number_per_page']
        self.redis_db = redis.StrictRedis(host=redis_host, port=redis_port, db=redis_db)
        # Initialize logger
        self._log = logging.getLogger(__name__)
        logging.getLogger(__name__).setLevel(loglevel)
        logging.basicConfig(format='%(asctime)s %(name)s %(levelname)s %(message)s',
                            handlers=[
                                logging.FileHandler(logfile),
                                logging.StreamHandler()
                            ])

    def timestamp_simhash(self, url, timestamp):
        if not url:
            self._log.error('did not give url parameter')
            return json.dumps({'error': 'URL is required.'})
        if not timestamp:
            self._log.error('did not give timestamp parameter')
            return json.dumps({'error': 'Timestamp is required.'})
        self._log.info('requesting redis db entry for %s %s', url, timestamp)
        results = self.redis_db.hget(surt(url), timestamp)
        if results:
            results = results.decode('utf-8')
            self._log.info('found entry %s', results)
            return json.dumps({'simhash': results})
        self._log.info('entry not found')
        return json.dumps({'simhash': 'None'})

    def year_simhash(self, url, year, page):
        if not url:
            self._log.error('did not give url parameter')
            return json.dumps({'error': 'URL is required.'})
        if not year:
            self._log.error('did not give year parameter')
            return json.dumps({'error': 'Year is required.'})
        if page is not None and page < 1:
            self._log.info('Page param needs to be bigger than zero')
            return json.dumps({'status': 'error', 'info': 'Page param needs to be bigger than zero.'})
        self._log.info('requesting redis db entry for %s %s', url, year)
        results = self.redis_db.hkeys(surt(url))
        if results:
            timestamps_to_fetch = []
            for timestamp in results:
                timestamp = timestamp.decode('UTF-8')
                timestamp_year = timestamp[:4]
                if timestamp_year == str(year):
                    timestamps_to_fetch.append(timestamp)
            if timestamps_to_fetch:
                return self.handle_results(timestamps_to_fetch, url, page)
        self._log.info('No simhases for this URL and Year')
        return json.dumps({'simhash': 'None'})

    def handle_results(self, timestamps_to_fetch, url, page):
        available_simhashes = []
        if page is not None:
            number_of_pages = ceil(len(timestamps_to_fetch) / self.snapshots_per_page)
            if page > number_of_pages:
                page = number_of_pages
            if number_of_pages > 0:
                timestamps_to_fetch = \
                    timestamps_to_fetch[(page - 1) * self.snapshots_per_page:(page * self.snapshots_per_page)]
            else:
                number_of_pages = 1
        results = self.redis_db.hmget(surt(url), timestamps_to_fetch)
        for i, simhash in enumerate(results):
            available_simhashes.append([str(timestamps_to_fetch[i]), simhash.decode('utf-8')])
        if page is not None:
            available_simhashes.insert(0,["pages", number_of_pages])
        return json.dumps(available_simhashes, separators=',:')

    def download_snapshot(self, snapshot, i):
        self._log.info('fetching snapshot %d out of %d', i, self.total)
        if (i - 1) % 10 == 0:
            self.update_state(task_id=self.job_id, state='PENDING',
                              meta={'info': str(i - 1) + ' captures have been processed'})
        response = self.make_request('/web/' + snapshot + 'id_/' + self.url, 0)
        self._log.info('calculating simhash for snapshot %d out of %d', i, self.total)
        return response

    def make_request(self, url, counter):
        if counter > 1:
            raise http.client.InvalidURL
        self.http.request('GET', url)
        response = self.http.getresponse()
        if 300 <= response.code < 400:
            location_header = response.getheader('Location')
            new_url = urlparse(location_header).path
            response.read()
            return self.make_request(new_url, counter + 1)
        return response.read().decode('utf-8', 'ignore')

    def start_profiling(self, snapshot, index):
        cProfile.runctx('self.get_calc_save(snapshot, index)',
                        globals=globals(), locals=locals(), filename='profile.prof')

    def get_calc_save(self, snapshot, index):
        response_data = self.download_snapshot(snapshot, index)
        data = self.calc_features(response_data)
        simhash = self.calculate_simhash(data)
        self.digest_dict[self.non_dup[snapshot]] = simhash
        self.save_to_redis(snapshot, simhash, index)

    def calc_features(self, response):

        # use html5parser to heal html
        e = html5parser.fromstring(response)
        # get etree element
        tree = fromstring(tostring(e))
        # get rid of embedded content (scripts, css)
        tree = clean_html(tree)
        # get rid of markup
        text = tree.text_content()
        # turn all characters to lowercase
        text = text.lower()
        # break into lines and remove leading and trailing space on each
        lines = (line.strip() for line in text.splitlines())
        # break multi-headlines into a line each
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        # drop blank lines
        text = '\n'.join(chunk for chunk in chunks if chunk)

        text = text.split()

        text = {k: sum(1 for _ in g) for k, g in groupby(sorted(text))}
        return text

    def calculate_simhash(self, text):
        temp_simhash = Simhash(text, self.simhash_size, hashfunc=hash_function).value
        self._log.info(temp_simhash)
        return temp_simhash

    def run(self, url, year):
        self.url = url
        time_started = datetime.datetime.now()
        self._log.info('calculate simhash started')
        if not self.url:
            self._log.error('did not give url parameter')
            result = {'status': 'error', 'info': 'URL is required.'}
        elif not year:
            self._log.error('did not give year parameter')
            result = {'status': 'error', 'info': 'Year is required.'}
        else:
            self.digest_dict = {}
            try:
                self._log.info('fetching timestamps of %s for year %s', self.url, year)
                self.update_state(state='PENDING',
                                  meta={'info': 'Fetching timestamps of '
                                                + self.url + ' for year ' + year})
                wayback_url = '/cdx/search/cdx?url=' + self.url + \
                              '&' + 'from=' + year + '&to=' + year + '&fl=timestamp,digest&output=json'
                if self.snapshots_number != -1:
                    wayback_url += '&limit=' + str(self.snapshots_number)
                response = self.make_request(wayback_url, 0)
                self._log.info('finished fetching timestamps of %s for year %s', self.url, year)
                snapshots = json.loads(response)

                if not snapshots:
                    self._log.error('no snapshots found for this year and url combination')
                    result = {'status': 'error',
                              'info': 'no snapshots found for this year and url combination'}
                    return json.dumps(result, sort_keys=True)
                snapshots.pop(0)
                self.total = len(snapshots)
                self.job_id = self.request.id

                self.non_dup = {}
                self.dup = {}
                for elem in snapshots:
                    if elem[1] in self.non_dup.values():
                        self.dup[elem[0]] = elem[1]
                    else:
                        self.non_dup[elem[0]] = elem[1]
                with concurrent.futures.ThreadPoolExecutor(max_workers=
                                                           self.thread_number) as executor:
                    # Start the load operations and mark each future with its URL
                    # future_to_url = {executor.submit(self.start_profiling,
                    #                                  snapshot, index):
                    future_to_url = {executor.submit(self.get_calc_save,
                                                     snapshot, index):
                                         snapshot for index, snapshot in enumerate(self.non_dup)}
                    for future in concurrent.futures.as_completed(future_to_url):
                        try:
                            future.result()
                        except Exception as exc:
                            self._log.error(exc)
                    for elem in self.dup:
                        self.save_to_redis(elem, self.digest_dict[self.dup[elem]], -1)
                    self.redis_db.expire(surt(self.url), self.simhash_expire)
            except Exception as exc:
                self._log.error(exc.args[0])
                result = {'status': 'error', 'info': exc.args[0]}
                return json.dumps(result, sort_keys=True)
            time_ended = datetime.datetime.now()
            result = {'duration': str((time_ended - time_started).seconds)}
            self._log.info('calculate simhash ended with duration: %d',
                           (time_ended - time_started).seconds)
            return json.dumps(result, sort_keys=True)
        return json.dumps(result, sort_keys=True)

    def save_to_redis(self, snapshot, data, index):
        self._log.info('saving to redis simhash for snapshot %d out of %d', index, self.total)
        self.redis_db.hset(surt(self.url), snapshot, base64.b64encode(struct.pack('L', data)))


def hash_function(x):
    return int(xxhash.xxh64(x).hexdigest(), 16)
