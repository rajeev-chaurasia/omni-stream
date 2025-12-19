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
                    const std::string &server, bool simulate) {
  NetworkClient client(server);

  if (simulate) {
    client.simulate(queue);
  } else if (client.connect()) {
    client.stream(queue);
  } else {
    client.simulate(queue);
  }

  std::cout << "[Network] Sent " << client.sent() << " packets" << std::endl;
}

int main(int argc, char *argv[]) {
  std::cout << "========================================\n"
            << "  OmniStream Telemetry Agent v1.0\n"
            << "  60Hz | C++17 | gRPC\n"
            << "========================================\n";

  std::string vehicle = "AV-001";
  std::string server = "localhost:50051";
  bool simulate = true;

  for (int i = 1; i < argc; ++i) {
    std::string arg = argv[i];
    if (arg == "--vehicle" && i + 1 < argc)
      vehicle = argv[++i];
    else if (arg == "--server" && i + 1 < argc)
      server = argv[++i];
    else if (arg == "--real")
      simulate = false;
    else if (arg == "--help") {
      std::cout
          << "Usage: omnistream [--vehicle ID] [--server ADDR] [--real]\n";
      return 0;
    }
  }

  std::cout << "Vehicle: " << vehicle << "\n"
            << "Server:  " << server << "\n"
            << "Mode:    " << (simulate ? "SIMULATE" : "LIVE") << "\n\n";

  std::signal(SIGINT, on_signal);
  std::signal(SIGTERM, on_signal);

  ThreadSafeQueue<std::unique_ptr<TelemetryPacket>> queue;

  std::thread physics(physics_thread, std::ref(queue), vehicle);
  std::thread network(network_thread, std::ref(queue), server, simulate);

  while (running) {
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
  }

  queue.shutdown();
  physics.join();
  network.join();

  std::cout << "OmniStream stopped.\n";
  return 0;
}