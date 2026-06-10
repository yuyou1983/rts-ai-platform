"""Proto generated modules — fix import path so generated 'from proto import xxx' works."""
import sys
import os

# protoc generates 'from proto import xxx' which needs simcore/proto_out on sys.path
_proto_out_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _proto_out_dir not in sys.path:
    sys.path.insert(0, _proto_out_dir)
