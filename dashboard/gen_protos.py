"""Generates the Python gRPC stubs for telemetry.proto into dashboard/generated."""

import os
import subprocess
import sys

DASHBOARD_DIR = os.path.dirname(os.path.abspath(__file__))
PROTO_DIR = os.path.join(os.path.dirname(DASHBOARD_DIR), "protos")
OUT_DIR = os.path.join(DASHBOARD_DIR, "generated")


def main():
    try:
        import grpc_tools  # noqa: F401
    except ImportError:
        print("grpcio-tools is required: pip install -r requirements.txt")
        return 1

    os.makedirs(OUT_DIR, exist_ok=True)
    open(os.path.join(OUT_DIR, "__init__.py"), "a").close()

    command = [
        sys.executable, "-m", "grpc_tools.protoc",
        f"--proto_path={PROTO_DIR}",
        f"--python_out={OUT_DIR}",
        f"--grpc_python_out={OUT_DIR}",
        os.path.join(PROTO_DIR, "telemetry.proto"),
    ]

    result = subprocess.call(command)
    if result == 0:
        print(f"Stubs written to {OUT_DIR}")
    return result


if __name__ == "__main__":
    sys.exit(main())
