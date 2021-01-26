from setuptools import setup

import site
import sys
site.ENABLE_USER_SITE = "--user" in sys.argv[1:]

setup(use_scm_version={"version_scheme": "guess-next-dev", "local_scheme": "dirty-tag"})

