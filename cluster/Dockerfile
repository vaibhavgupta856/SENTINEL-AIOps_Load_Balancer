FROM ubuntu:22.04

# Install dependencies
RUN apt-get update && apt-get install -y \
    g++ \
    make \
    python3 \
    iputils-ping \
    curl \
    net-tools

WORKDIR /app
COPY monitor.cpp receiver.py chaos_state.py ./

# Compile C++ Hardware Monitor (Linux version with socket support)
RUN g++ -o monitor monitor.cpp -std=c++11

# Create flag directory for orchestrator communication
RUN mkdir -p /tmp

# Expose ports: 8080 (Health) and 8081 (Workload/API)
EXPOSE 8080 8081

# Run both C++ monitor and Python API server in parallel
CMD bash -c "./monitor 8080 \"${NODE_ID:-default}\" & python3 receiver.py"