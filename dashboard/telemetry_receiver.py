"""
OmniStream Dashboard Server

Bridges telemetry from the C++ gRPC agent to browser dashboards via WebSocket.
Supports both live gRPC mode and standalone simulation for demos.
"""

import asyncio
import json
import math
import time
import argparse
import threading
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler

import websockets

try:
    import grpc
    from generated import telemetry_pb2, telemetry_pb2_grpc
    GRPC_AVAILABLE = True
except ImportError:
    GRPC_AVAILABLE = False


WEBSOCKET_PORT = 8765
HTTP_PORT = 8000
TICK_RATE = 60


class TelemetrySimulator:
    """Generates synthetic telemetry matching the C++ agent output."""
    
    def __init__(self, vehicle_id="AV-001", lidar_points=1024):
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
            "tick": self.tick
        }


class GrpcReceiver:
    """Receives telemetry from C++ agent via gRPC streaming."""
    
    def __init__(self, server_address="localhost:50051"):
        self.server_address = server_address
        self.channel = None
        self.stub = None
    
    def connect(self):
        if not GRPC_AVAILABLE:
            print("[gRPC] Proto files not found. Run: python -m grpc_tools.protoc ...")
            return False
        
        try:
            self.channel = grpc.insecure_channel(self.server_address)
            self.stub = telemetry_pb2_grpc.TelemetryStreamStub(self.channel)
            print(f"[gRPC] Connected to {self.server_address}")
            return True
        except Exception as e:
            print(f"[gRPC] Connection failed: {e}")
            return False
    
    def stream(self):
        """Yields telemetry packets from the C++ agent."""
        if not self.stub:
            return
        
        try:
            for packet in self.stub.StreamTelemetry(iter([])):
                yield {
                    "vehicle_id": packet.vehicle_id,
                    "timestamp": packet.timestamp,
                    "lidar_scan": list(packet.lidar_scan),
                    "imu_reading": {
                        "accel_x": packet.imu_reading.accel_x,
                        "accel_y": packet.imu_reading.accel_y,
                        "accel_z": packet.imu_reading.accel_z,
                    },
                    "battery_level": packet.battery_level,
                    "tick": 0
                }
        except grpc.RpcError as e:
            print(f"[gRPC] Stream error: {e}")


class DashboardServer:
    """WebSocket server broadcasting telemetry to connected browsers."""
    
    def __init__(self, mode="simulate", grpc_address="localhost:50051"):
        self.mode = mode
        self.grpc_address = grpc_address
        self.clients = set()
        self.running = False
        self.packets_sent = 0
        self.last_log = time.time()
        
        if mode == "simulate":
            self.simulator = TelemetrySimulator()
        else:
            self.grpc_receiver = GrpcReceiver(grpc_address)
    
    async def register(self, websocket):
        self.clients.add(websocket)
        print(f"[WS] Client connected ({len(self.clients)} total)")
        await websocket.send(json.dumps({
            "type": "connected",
            "mode": self.mode
        }))
    
    async def unregister(self, websocket):
        self.clients.discard(websocket)
        print(f"[WS] Client disconnected ({len(self.clients)} total)")
    
    async def broadcast(self, message):
        if self.clients:
            websockets.broadcast(self.clients, message)
    
    async def handler(self, websocket):
        await self.register(websocket)
        try:
            async for _ in websocket:
                pass
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            await self.unregister(websocket)
    
    async def telemetry_loop(self):
        print(f"[Server] Mode: {self.mode.upper()} | Rate: {TICK_RATE}Hz")
        frame_time = 1.0 / TICK_RATE
        
        if self.mode == "grpc":
            if not self.grpc_receiver.connect():
                print("[Server] Falling back to simulation mode")
                self.mode = "simulate"
                self.simulator = TelemetrySimulator()
        
        while self.running:
            start = time.time()
            
            if self.mode == "simulate":
                packet = self.simulator.next_packet()
            else:
                # In real gRPC mode, we'd pull from a queue populated by gRPC stream
                packet = self.simulator.next_packet()  # Placeholder
            
            await self.broadcast(json.dumps({"type": "telemetry", "data": packet}))
            self.packets_sent += 1
            
            if time.time() - self.last_log >= 1.0:
                print(f"[Server] Tick {self.packets_sent} | Clients: {len(self.clients)}")
                self.last_log = time.time()
            
            await asyncio.sleep(max(0, frame_time - (time.time() - start)))
    
    async def start(self):
        self.running = True
        async with websockets.serve(self.handler, "0.0.0.0", WEBSOCKET_PORT):
            print(f"[Server] WebSocket on ws://0.0.0.0:{WEBSOCKET_PORT}")
            await self.telemetry_loop()


def serve_static():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    HTTPServer(("0.0.0.0", HTTP_PORT), SimpleHTTPRequestHandler).serve_forever()


def main():
    parser = argparse.ArgumentParser(description="OmniStream Dashboard")
    parser.add_argument("--mode", choices=["simulate", "grpc"], default="simulate")
    parser.add_argument("--grpc-server", default="localhost:50051")
    args = parser.parse_args()
    
    print("=" * 50)
    print("  OmniStream Dashboard Server")
    print("=" * 50)
    print(f"  Mode:      {args.mode.upper()}")
    print(f"  Dashboard: http://localhost:{HTTP_PORT}")
    print(f"  WebSocket: ws://localhost:{WEBSOCKET_PORT}")
    print("=" * 50)
    
    threading.Thread(target=serve_static, daemon=True).start()
    
    server = DashboardServer(mode=args.mode, grpc_address=args.grpc_server)
    
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        print("\n[Server] Stopped")


if __name__ == "__main__":
    main()
