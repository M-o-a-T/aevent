#!/bin/sh

# run tests

if ! test -d .git ; then
    echo "You need to be in the root source directory." >&2
    exit 1
fi

export PYTHONPATH=src:sample/pyroute2:tests/pyroute2:../anyio/src:../greenback

if test $# = 0 ; then set -- tests; fi
python3 -mpytest "$@"
