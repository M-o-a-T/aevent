import aevent
import os
backend = os.environ.get("AEVENT_BACKEND","trio")
aevent.setup(backend)

