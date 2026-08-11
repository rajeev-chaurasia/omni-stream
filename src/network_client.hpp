#pragma once

#include <atomic>
#include <chrono>
#include <iostream>
#include <memory>
#include <string>
#include <thread>

#include "telemetry.grpc.pb.h"
#include "telemetry.pb.h"
#include "thread_safe_queue.hpp"
#include <grpcpp/grpcpp.h>

namespace omnistream {

// gRPC streaming client that consumes packets from queue and sends to server.
class NetworkClient {
public:
  explicit NetworkClient(const std::string &address)
      : address_(address), connected_(false), sent_(0), acked_(0) {}

  bool connect(std::chrono::seconds timeout = std::chrono::seconds(5)) {
    channel_ =
        grpc::CreateChannel(address_, grpc::InsecureChannelCredentials());
    stub_ = TelemetryStream::NewStub(channel_);

    auto deadline = std::chrono::system_clock::now() + timeout;
    if (!channel_->WaitForConnected(deadline)) {
      std::cout << "[Network] No collector at " << address_ << " after "
                << timeout.count() << "s" << std::endl;
      return false;
    }

    connected_ = true;
    std::cout << "[Network] Connected to " << address_ << std::endl;
    return true;
  }

  void stream(ThreadSafeQueue<std::unique_ptr<TelemetryPacket>> &queue) {
    if (!connected_) {
      drain(queue);
      return;
    }

    grpc::ClientContext ctx;
    auto call = stub_->StreamTelemetry(&ctx);

    // Acks must be drained continuously. Leaving them in the receive window
    // would stall the server's writes, which stalls its reads, which blocks
    // Write() below once the HTTP/2 flow control window closes.
    std::thread ack_reader([this, &call] {
      ServerAck ack;
      while (call->Read(&ack)) {
        if (ack.success())
          acked_++;
      }
    });

    // Ownership of the packet moves out of the queue, so the payload is
    // serialized straight from the physics thread's allocation.
    while (auto packet = queue.pop()) {
      if (!call->Write(**packet)) {
        std::cout << "[Network] Write failed, collector went away" << std::endl;
        break;
      }
      log_progress(queue.size());
    }

    call->WritesDone();
    ack_reader.join();

    auto status = call->Finish();
    if (status.ok()) {
      std::cout << "[Network] Stream closed cleanly" << std::endl;
    } else {
      std::cout << "[Network] Stream closed: " << status.error_message() << " ("
                << status.error_code() << ")" << std::endl;
    }
  }

  // Offline path: keeps the pipeline moving when there is no collector so the
  // physics thread is not blocked by a full queue. Nothing leaves the process.
  void drain(ThreadSafeQueue<std::unique_ptr<TelemetryPacket>> &queue) {
    std::cout << "[Network] OFFLINE, discarding packets without sending"
              << std::endl;

    uint64_t dropped = 0;
    while (queue.pop()) {
      if (++dropped % 300 == 0) {
        std::cout << "[Network] OFFLINE, discarded " << dropped << " packets"
                  << std::endl;
      }
    }

    std::cout << "[Network] OFFLINE, discarded " << dropped << " packets total"
              << std::endl;
  }

  uint64_t sent() const { return sent_; }
  uint64_t acked() const { return acked_; }

private:
  void log_progress(size_t queue_size) {
    sent_++;
    if (sent_ % 60 == 0) {
      std::cout << "[Network] Sent " << sent_ << " | Acked " << acked_
                << " | Queue: " << queue_size << std::endl;
    }
  }

  std::string address_;
  std::shared_ptr<grpc::Channel> channel_;
  std::unique_ptr<TelemetryStream::Stub> stub_;
  std::atomic<bool> connected_;
  std::atomic<uint64_t> sent_;
  std::atomic<uint64_t> acked_;
};

} // namespace omnistream
