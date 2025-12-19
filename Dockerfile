# Multi-stage build: Build in Ubuntu, run in minimal image
# Stage 1: Build
FROM ubuntu:22.04 AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    git \
    pkg-config \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Install gRPC and Protobuf from source (for latest version)
WORKDIR /opt
RUN git clone --recurse-submodules -b v1.60.0 --depth 1 https://github.com/grpc/grpc && \
    cd grpc && \
    mkdir -p cmake/build && \
    cd cmake/build && \
    cmake -DgRPC_INSTALL=ON \
          -DgRPC_BUILD_TESTS=OFF \
          -DCMAKE_INSTALL_PREFIX=/usr/local \
          ../.. && \
    make -j$(nproc) && \
    make install

# Copy project source
WORKDIR /app
COPY CMakeLists.txt .
COPY protos/ protos/
COPY src/ src/

# Build OmniStream
RUN mkdir build && cd build && \
    cmake -DCMAKE_PREFIX_PATH=/usr/local .. && \
    make -j$(nproc)

# Stage 2: Runtime (minimal image)
FROM ubuntu:22.04-slim AS runtime

# Install only runtime dependencies
RUN apt-get update && apt-get install -y \
    libssl3 \
    && rm -rf /var/lib/apt/lists/*

# Copy built binary and shared libraries
COPY --from=builder /app/build/omnistream /usr/local/bin/
COPY --from=builder /usr/local/lib/lib*.so* /usr/local/lib/

# Update library path
RUN ldconfig

# Set working directory
WORKDIR /app

# Default command
ENTRYPOINT ["omnistream"]
CMD ["--help"]
