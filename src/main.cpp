#include <atomic>
#include <chrono>
#include <csignal>
#include <iostream>
#include <thread>

#include "network_client.hpp"
#include "sensor_generator.hpp"
#include "telemetry.pb.h"
#include "thread_safe_queue.hpp"

using namespace omnistream;

std::atomic<bool> running{true};

void on_signal(int) {
  std::cout << "\nShutting down..." << std::endl;
  running = false;
}

void physics_thread(ThreadSafeQueue<std::unique_ptr<TelemetryPacket>> &queue,
                    const std::string &vehicle_id) {
  SensorGenerator sensor(vehicle_id);
  const auto frame = std::chrono::microseconds(16667); // 60 Hz

  while (running) {
    auto start = std::chrono::steady_clock::now();

    if (!queue.push(sensor.generate()))
      break;

    if (sensor.tick() % 60 == 0) {
      std::cout << "[Physics] Tick " << sensor.tick()
                << " | Queue: " << queue.size() << std::endl;
    }

    auto elapsed = std::chrono::steady_clock::now() - start;
    std::this_thread::sleep_for(frame - elapsed);
  }

  std::cout << "[Physics] Stopped at tick " << sensor.tick() << std::endl;
}

void network_thread(ThreadSafeQueue<std::unique_ptr<TelemetryPacket>> &queue,
                    const std::string &server, bool offline) {
  NetworkClient client(server);

  if (offline) {
    client.drain(queue);
  } else if (client.connect()) {
    client.stream(queue);
  } else {
    client.drain(queue);
  }

  std::cout << "[Network] Sent " << client.sent() << " packets, "
            << client.acked() << " acked" << std::endl;

  // The consumer is finished, so release the producer instead of leaving it
  // blocked on a queue nobody drains.
  running = false;
  queue.shutdown();
}

int main(int argc, char *argv[]) {
  std::cout << "========================================\n"
            << "  OmniStream Telemetry Agent v1.0\n"
            << "  60Hz | C++17 | gRPC\n"
            << "========================================\n";

  std::string vehicle = "AV-001";
  std::string server = "localhost:50051";
  bool offline = false;

  for (int i = 1; i < argc; ++i) {
    std::string arg = argv[i];
    if (arg == "--vehicle" && i + 1 < argc)
      vehicle = argv[++i];
    else if (arg == "--server" && i + 1 < argc)
      server = argv[++i];
    else if (arg == "--offline")
      offline = true;
    else if (arg == "--help") {
      std::cout << "Usage: omnistream [--vehicle ID] [--server ADDR] "
                   "[--offline]\n"
                << "  --vehicle ID   Vehicle identifier (default: AV-001)\n"
                << "  --server ADDR  Collector address (default: "
                   "localhost:50051)\n"
                << "  --offline      Generate without streaming anywhere\n";
      return 0;
    }
  }

  std::cout << "Vehicle: " << vehicle << "\n"
            << "Server:  " << server << "\n"
            << "Mode:    " << (offline ? "OFFLINE (nothing is sent)" : "LIVE")
            << "\n\n";

  std::signal(SIGINT, on_signal);
  std::signal(SIGTERM, on_signal);

  ThreadSafeQueue<std::unique_ptr<TelemetryPacket>> queue;

  std::thread physics(physics_thread, std::ref(queue), vehicle);
  std::thread network(network_thread, std::ref(queue), server, offline);

  while (running) {
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
  }

  queue.shutdown();
  physics.join();
  network.join();

  std::cout << "OmniStream stopped.\n";
  return 0;
}