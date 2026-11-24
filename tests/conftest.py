import os
import tempfile

# Tests must never touch the developer's real database or media folders.
# Set before anything imports mediamind.api.
_tmp = tempfile.mkdtemp(prefix="mm_test_")
os.environ["MEDIAMIND_DB"] = os.path.join(_tmp, "test.sqlite")
os.environ["MEDIAMIND_DATA"] = os.path.join(_tmp, "data")
os.environ["MEDIAMIND_TRACES"] = os.path.join(_tmp, "traces")
# Most tests exercise one layer with an explicit user_id; tests/test_auth.py turns login back on.
os.environ["MEDIAMIND_AUTH"] = "off"
