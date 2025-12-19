#pragma once

#include <condition_variable>
#include <mutex>
#include <optional>
#include <queue>

namespace omnistream {

// Thread-safe FIFO queue with blocking push/pop and graceful shutdown.
// Uses mutex + condition variable (upgrade to lock-free for lower latency).
template <typename T> class ThreadSafeQueue {
public:
  explicit ThreadSafeQueue(size_t capacity = 1000)
      : capacity_(capacity), shutdown_(false) {}

  bool push(T item) {
    std::unique_lock<std::mutex> lock(mutex_);
    not_full_.wait(lock,
                   [this] { return queue_.size() < capacity_ || shutdown_; });

    if (shutdown_)
      return false;

    queue_.push(std::move(item));
    lock.unlock();
    not_empty_.notify_one();
    return true;
  }

  std::optional<T> pop() {
    std::unique_lock<std::mutex> lock(mutex_);
    not_empty_.wait(lock, [this] { return !queue_.empty() || shutdown_; });

    if (shutdown_ && queue_.empty())
      return std::nullopt;

    T item = std::move(queue_.front());
    queue_.pop();
    lock.unlock();
    not_full_.notify_one();
    return item;
  }

  void shutdown() {
    {
      std::lock_guard<std::mutex> lock(mutex_);
      shutdown_ = true;
    }
    not_empty_.notify_all();
    not_full_.notify_all();
  }

  size_t size() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return queue_.size();
  }

private:
  std::queue<T> queue_;
  size_t capacity_;
  bool shutdown_;
  mutable std::mutex mutex_;
  std::condition_variable not_empty_;
  std::condition_variable not_full_;
};

} // namespace omnistream
