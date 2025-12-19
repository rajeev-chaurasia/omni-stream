#pragma once

#include <chrono>
#include <cmath>
#include <memory>
#include <string>
#include <vector>

#include "telemetry.pb.h"

namespace omnistream {

// Generates synthetic sensor data mimicking an autonomous vehicle.
// Uses pre-allocated buffers to avoid memory churn in the hot loop.
class SensorGenerator {
public:
  SensorGenerator(const std::string &vehicle_id, size_t lidar_points = 1024)
      : vehicle_id_(vehicle_id), lidar_points_(lidar_points), tick_(0),
        battery_(100.0f) {
    lidar_buffer_.reserve(lidar_points_);
  }

  std::unique_ptr<TelemetryPacket> generate() {
    auto packet = std::make_unique<TelemetryPacket>();

    packet->set_vehicle_id(vehicle_id_);
    packet->set_timestamp(now_micros());

    fill_lidar(packet.get());
    fill_imu(packet.get());

    battery_ = std::max(0.0f, battery_ - 0.0001f);
    packet->set_battery_level(battery_);

    tick_++;
    return packet;
  }

  uint64_t tick() const { return tick_; }

private:
  void fill_lidar(TelemetryPacket *pkt) {
    lidar_buffer_.clear();

    for (size_t i = 0; i < lidar_points_; ++i) {
      float angle = static_cast<float>(i) / lidar_points_ * 2.0f * M_PI;
      float dist = 10.0f + std::sin(tick_ * 0.05f + angle * 4.0f) * 2.0f;
      lidar_buffer_.push_back(dist);
    }

    pkt->mutable_lidar_scan()->Add(lidar_buffer_.begin(), lidar_buffer_.end());
  }

  void fill_imu(TelemetryPacket *pkt) {
    float t = tick_ * 0.02f;
    auto *imu = pkt->mutable_imu_reading();
    imu->set_accel_x(std::sin(t) * 0.5f);
    imu->set_accel_y(std::cos(t * 0.7f) * 0.3f);
    imu->set_accel_z(9.81f + std::sin(t * 2.0f) * 0.1f);
  }

  int64_t now_micros() {
    auto now = std::chrono::system_clock::now();
    return std::chrono::duration_cast<std::chrono::microseconds>(
               now.time_since_epoch())
        .count();
  }

  std::string vehicle_id_;
  size_t lidar_points_;
  uint64_t tick_;
  float battery_;
  std::vector<float> lidar_buffer_;
};

} // namespace omnistream
