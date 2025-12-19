cmake_minimum_required(VERSION 3.15)
project(OmniStream)

# Use C++ 17
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Find required packages
find_package(Threads REQUIRED)
find_package(Protobuf CONFIG REQUIRED)
find_package(gRPC CONFIG REQUIRED)

# Find protoc and grpc_cpp_plugin executables
find_program(PROTOC_EXECUTABLE protoc REQUIRED)
find_program(GRPC_CPP_PLUGIN grpc_cpp_plugin REQUIRED)

message(STATUS "Found protoc: ${PROTOC_EXECUTABLE}")
message(STATUS "Found grpc_cpp_plugin: ${GRPC_CPP_PLUGIN}")

# Proto file location
set(PROTO_FILE "${CMAKE_CURRENT_SOURCE_DIR}/protos/telemetry.proto")
set(PROTO_OUT_DIR "${CMAKE_CURRENT_BINARY_DIR}/generated")

# Create output directory
file(MAKE_DIRECTORY ${PROTO_OUT_DIR})

# Generate protobuf and gRPC sources
set(PROTO_SRCS "${PROTO_OUT_DIR}/telemetry.pb.cc")
set(PROTO_HDRS "${PROTO_OUT_DIR}/telemetry.pb.h")
set(GRPC_SRCS "${PROTO_OUT_DIR}/telemetry.grpc.pb.cc")
set(GRPC_HDRS "${PROTO_OUT_DIR}/telemetry.grpc.pb.h")

add_custom_command(
    OUTPUT ${PROTO_SRCS} ${PROTO_HDRS} ${GRPC_SRCS} ${GRPC_HDRS}
    COMMAND ${PROTOC_EXECUTABLE}
        --proto_path=${CMAKE_CURRENT_SOURCE_DIR}/protos
        --cpp_out=${PROTO_OUT_DIR}
        --grpc_out=${PROTO_OUT_DIR}
        --plugin=protoc-gen-grpc=${GRPC_CPP_PLUGIN}
        ${PROTO_FILE}
    DEPENDS ${PROTO_FILE}
    COMMENT "Generating protobuf and gRPC sources..."
)

# Create a library for generated proto files
add_library(proto_lib STATIC ${PROTO_SRCS} ${GRPC_SRCS})
target_include_directories(proto_lib PUBLIC ${PROTO_OUT_DIR})
target_link_libraries(proto_lib PUBLIC 
    protobuf::libprotobuf 
    gRPC::grpc++
)

# Main executable
add_executable(omnistream src/main.cpp)
target_include_directories(omnistream PRIVATE 
    ${CMAKE_CURRENT_SOURCE_DIR}/src
    ${PROTO_OUT_DIR}
)
target_link_libraries(omnistream 
    proto_lib
    Threads::Threads
    gRPC::grpc++ 
    protobuf::libprotobuf
)