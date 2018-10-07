#!/usr/bin/env bash
#Run Redis server
redis-server &

export WAYBACK_DISCOVER_DIFF_CONF=tests/testconf.yml

#Run tests
pytest -vv
