"""
gRPC half of the OmniStream dashboard.

The C++ agent is the gRPC client: it dials in and writes TelemetryPacket
messages. This module implements the server side of StreamTelemetry, acking
every packet it hands to the dashboard bridge.
"""

import os
import sys
import time

GENERATED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generated")
if GENERATED_DIR not in sys.path:
    sys.path.insert(0, GENERATED_DIR)

import grpc

import telemetry_pb2
import telemetry_pb2_grpc

SOURCE_AGENT = "cpp-agent"


def now_micros():
    return int(time.time() * 1_000_000)


def to_payload(packet, tick):
    """Converts a TelemetryPacket into the JSON shape the browser expects."""
    return {
        "vehicle_id": packet.vehicle_id,
        "timestamp": packet.timestamp,
        "lidar_scan": [round(distance, 3) for distance in packet.lidar_scan],
        "imu_reading": {
            "accel_x": round(packet.imu_reading.accel_x, 4),
            "accel_y": round(packet.imu_reading.accel_y, 4),
            "accel_z": round(packet.imu_reading.accel_z, 4),
        },
        "battery_level": round(packet.battery_level, 4),
        "tick": tick,
        "source": SOURCE_AGENT,
        "simulated": False,
    }


class TelemetryCollector(telemetry_pb2_grpc.TelemetryStreamServicer):
    """Receives telemetry streams from C++ agents and acks each packet."""

    def __init__(self, on_packet):
        self._on_packet = on_packet
        self.packets = 0
        self.agents = 0

    async def StreamTelemetry(self, request_iterator, context):
        self.agents += 1
        peer = context.peer()
        received = 0
        print(f"[gRPC] Agent stream opened from {peer}", flush=True)

        try:
            async for packet in request_iterator:
                received += 1
                self.packets += 1

                # websockets.broadcast() never waits, so a slow browser grows its
                # own write buffer rather than throttling the agent. Only this
                # loop stopping closes the HTTP/2 window and blocks the agent.
                await self._on_packet(to_payload(packet, self.packets))

                yield telemetry_pb2.ServerAck(
                    success=True, received_timestamp=now_micros()
                )
        finally:
            print(
                f"[gRPC] Agent stream from {peer} closed after {received} packets",
                flush=True,
            )


async def serve(collector, port):
    """Starts the TelemetryStream service and returns the running server."""
    server = grpc.aio.server()
    telemetry_pb2_grpc.add_TelemetryStreamServicer_to_server(collector, server)
    server.add_insecure_port(f"0.0.0.0:{port}")

    await server.start()
    print(f"[gRPC] TelemetryStream listening on 0.0.0.0:{port}", flush=True)
    return server
