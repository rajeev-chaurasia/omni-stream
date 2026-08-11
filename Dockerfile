# Multi-stage build: Build in Ubuntu, run in a slim runtime image
# Stage 1: Build
FROM ubuntu:22.04 AS builder

# Ubuntu ships gRPC 1.30 and Protobuf 3.12, which is all this agent needs.
# Building gRPC from source here costs tens of minutes for no benefit.
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    build-essential \
    cmake \
    pkg-config \
    libgrpc++-dev \
    libprotobuf-dev \
    protobuf-compiler \
    protobuf-compiler-grpc \
    && rm -rf /var/lib/apt/lists/*

# Copy project source
WORKDIR /app
COPY CMakeLists.txt .
COPY protos/ protos/
COPY src/ src/

# Build OmniStream
RUN mkdir build && cd build && \
    cmake .. && \
    make -j$(nproc)

# Stage 2: Runtime
FROM ubuntu:22.04 AS runtime

# Shared libraries the agent links against, without the headers or toolchain
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    libgrpc++1 \
    libprotobuf23 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/build/omnistream /usr/local/bin/

WORKDIR /app

ENTRYPOINT ["omnistream"]
CMD ["--help"]
