#pragma once

#include <atomic>
#include <iostream>
#include <memory>
#include <string>

#include "telemetry.grpc.pb.h"
#include "telemetry.pb.h"
#include "thread_safe_queue.hpp"
#include <grpcpp/grpcpp.h>

namespace omnistream {

// gRPC streaming client that consumes packets from queue and sends to server.
class NetworkClient {
public:
  explicit NetworkClient(const std::string &address)
      : address_(address), connected_(false), sent_(0) {}

  bool connect() {
    channel_ =
        grpc::CreateChannel(address_, grpc::InsecureChannelCredentials());
    stub_ = TelemetryStream::NewStub(channel_);
    connected_ = true;
    std::cout << "[Network] Connected to " << address_ << std::endl;
    return true;
  }

  void stream(ThreadSafeQueue<std::unique_ptr<TelemetryPacket>> &queue) {
    if (!connected_) {
      simulate(queue);
      return;
    }

    grpc::ClientContext ctx;
    auto stream = stub_->StreamTelemetry(&ctx);

    while (auto packet = queue.pop()) {
      if (!stream->Write(**packet))
        break;
      log_progress(queue.size());
    }

    stream->WritesDone();
    auto status = stream->Finish();
    std::cout << "[Network] Stream closed: " << status.error_message()
              << std::endl;
  }

  void simulate(ThreadSafeQueue<std::unique_ptr<TelemetryPacket>> &queue) {
    std::cout << "[Network] Running in simulation mode" << std::endl;

    while (auto packet = queue.pop()) {
      log_progress(queue.size());
    }

    std::cout << "[Network] Simulation done. Packets: " << sent_ << std::endl;
  }

  uint64_t sent() const { return sent_; }

private:
  void log_progress(size_t queue_size) {
    sent_++;
    if (sent_ % 60 == 0) {
      std::cout << "[Network] Sent " << sent_ << " | Queue: " << queue_size
                << std::endl;
    }
  }

  std::string address_;
  std::shared_ptr<grpc::Channel> channel_;
  std::unique_ptr<TelemetryStream::Stub> stub_;
  std::atomic<bool> connected_;
  std::atomic<uint64_t> sent_;
};

} // namespace omnistream
