"""
OmniStream Dashboard Server

Hosts the TelemetryStream gRPC service that C++ agents stream into, and relays
every packet it receives to browser dashboards over WebSocket.

A synthetic fallback source is available for demos without a built agent. It is
not the real path: nothing crosses gRPC in that mode, and every packet it emits
is tagged so the dashboard says so.
"""

import argparse
import asyncio
import json
import math
import os
import sys
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler

import websockets

WEBSOCKET_PORT = 8765
HTTP_PORT = 8000
GRPC_PORT = 50051
TICK_RATE = 60

SOURCE_FALLBACK = "fallback-simulator"


class FallbackSimulator:
    """Synthetic telemetry for demos with no agent running.

    Mirrors the C++ generator's math so the panels look alive, but it is a
    stand-in rather than a second implementation of the product path.
    """

    def __init__(self, vehicle_id="SIM-001", lidar_points=1024):
        self.vehicle_id = vehicle_id
        self.lidar_points = lidar_points
        self.tick = 0
        self.battery = 100.0

    def next_packet(self):
        t = self.tick * 0.02

        lidar = [
            round(10.0 + math.sin(self.tick * 0.05 + (i / self.lidar_points) * 8 * math.pi) * 2.0, 3)
            for i in range(self.lidar_points)
        ]

        imu = {
            "accel_x": round(math.sin(t) * 0.5, 4),
            "accel_y": round(math.cos(t * 0.7) * 0.3, 4),
            "accel_z": round(9.81 + math.sin(t * 2.0) * 0.1, 4)
        }

        self.battery = max(0.0, self.battery - 0.0001)
        self.tick += 1

        return {
            "vehicle_id": self.vehicle_id,
            "timestamp": int(time.time() * 1_000_000),
            "lidar_scan": lidar,
            "imu_reading": imu,
            "battery_level": round(self.battery, 4),
            "tick": self.tick,
            "source": SOURCE_FALLBACK,
            "simulated": True
        }


class DashboardServer:
    """WebSocket server broadcasting telemetry to connected browsers."""

    def __init__(self, mode="grpc", grpc_port=GRPC_PORT):
        self.mode = mode
        self.grpc_port = grpc_port
        self.clients = set()
        self.packets_relayed = 0
        self.last_log = time.monotonic()

    async def register(self, websocket):
        self.clients.add(websocket)
        print(f"[WS] Client connected ({len(self.clients)} total)")
        await websocket.send(json.dumps({
            "type": "connected",
            "mode": self.mode,
            "simulated": self.mode != "grpc"
        }))

    async def unregister(self, websocket):
        self.clients.discard(websocket)
        print(f"[WS] Client disconnected ({len(self.clients)} total)")

    async def handler(self, websocket):
        await self.register(websocket)
        try:
            async for _ in websocket:
                pass
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            await self.unregister(websocket)

    async def relay(self, packet):
        """Fans one telemetry packet out to every connected browser."""
        if self.clients:
            websockets.broadcast(self.clients, json.dumps({"type": "telemetry", "data": packet}))

        self.packets_relayed += 1

        if time.monotonic() - self.last_log >= 1.0:
            print(f"[Server] Relayed {self.packets_relayed} packets from "
                  f"{packet['source']} | Clients: {len(self.clients)}")
            self.last_log = time.monotonic()

    async def collect_from_agents(self):
        from telemetry_service import TelemetryCollector, serve

        collector = TelemetryCollector(self.relay)
        server = await serve(collector, self.grpc_port)
        print("[Server] Waiting for agents. Start one with: "
              f"omnistream --server localhost:{self.grpc_port}")
        await server.wait_for_termination()

    async def run_fallback(self):
        print(f"[Server] FALLBACK simulator at {TICK_RATE}Hz, no agent involved")
        simulator = FallbackSimulator()
        frame_time = 1.0 / TICK_RATE

        while True:
            start = time.monotonic()
            await self.relay(simulator.next_packet())
            await asyncio.sleep(max(0, frame_time - (time.monotonic() - start)))

    async def start(self):
        async with websockets.serve(self.handler, "0.0.0.0", WEBSOCKET_PORT):
            print(f"[Server] WebSocket on ws://0.0.0.0:{WEBSOCKET_PORT}")
            if self.mode == "grpc":
                await self.collect_from_agents()
            else:
                await self.run_fallback()


def serve_static():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    HTTPServer(("0.0.0.0", HTTP_PORT), SimpleHTTPRequestHandler).serve_forever()


def missing_grpc_dependency():
    """Returns the import error blocking live mode, or None if it is usable."""
    try:
        import telemetry_service  # noqa: F401
        return None
    except ImportError as exc:
        return exc


def main():
    parser = argparse.ArgumentParser(description="OmniStream Dashboard")
    parser.add_argument("--mode", choices=["grpc", "simulate"], default="grpc",
                        help="grpc: receive from C++ agents. simulate: synthetic fallback")
    parser.add_argument("--grpc-port", type=int, default=GRPC_PORT)
    args = parser.parse_args()

    if args.mode == "grpc":
        error = missing_grpc_dependency()
        if error:
            print(f"[gRPC] Live mode unavailable: {error}")
            print("[gRPC] Generate the Python stubs:  python3 gen_protos.py")
            print("[gRPC] Install dependencies:       pip install -r requirements.txt")
            print("[gRPC] Or run without an agent:    python3 telemetry_receiver.py --mode simulate")
            return 1

    source = ("C++ AGENT over gRPC" if args.mode == "grpc"
              else "FALLBACK SIMULATOR (synthetic, no agent, no gRPC)")

    print("=" * 50)
    print("  OmniStream Dashboard Server")
    print("=" * 50)
    print(f"  Source:    {source}")
    if args.mode == "grpc":
        print(f"  gRPC in:   0.0.0.0:{args.grpc_port}")
    print(f"  Dashboard: http://localhost:{HTTP_PORT}")
    print(f"  WebSocket: ws://localhost:{WEBSOCKET_PORT}")
    print("=" * 50)

    threading.Thread(target=serve_static, daemon=True).start()

    server = DashboardServer(mode=args.mode, grpc_port=args.grpc_port)

    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        print("\n[Server] Stopped")

    return 0


if __name__ == "__main__":
    sys.exit(main())
