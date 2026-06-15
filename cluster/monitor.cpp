#include <iostream>
#include <string>
#include <sstream>
#include <ctime>
#include <unistd.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <cstring>
#include <fstream>
#include <thread>
#include <algorithm>

using namespace std;

// Simulate CPU load from workload
int simulated_load = 0;
int node_cpu_bias = 0;
int node_ram_bias = 0;
int node_temp_bias = 0;

unsigned int hashNodeId(const char* nodeId) {
    unsigned int hash = 5381;
    while (*nodeId) {
        hash = ((hash << 5) + hash) + static_cast<unsigned char>(*nodeId++);
    }
    return hash;
}

string getMetrics(int port) {
    // Dynamic metrics calculation with simulated workload (unique per node)
    int baseCpuLoad = 15 + (rand() % 20) + node_cpu_bias;
    int cpuLoad = min(95, baseCpuLoad + simulated_load);
    int ramUsage = 35 + (rand() % 20) + node_ram_bias;

    // Simulated die temperature rises with compute load (low-level thermal sensor)
    int tempC = 32 + (cpuLoad * 48 / 100) + node_temp_bias + (rand() % 4);
    
    // Check for load flag (Triggered by Orchestrator for stress testing)
    ifstream file("/tmp/job_active.flag");
    if (file.good()) {
        cpuLoad = min(98, 85 + (rand() % 13));
        tempC = min(96, 72 + (rand() % 18));
        file.close();
    }

    // Chaos CPU spike flag from receiver
    ifstream chaosFile("/tmp/chaos_cpu.flag");
    if (chaosFile.good()) {
        cpuLoad = min(98, 90 + (rand() % 8));
        tempC = min(98, 82 + (rand() % 12));
        chaosFile.close();
    }

    // Chaos thermal spike flag from receiver
    ifstream thermalFile("/tmp/chaos_thermal.flag");
    if (thermalFile.good()) {
        tempC = min(99, 86 + (rand() % 10));
        thermalFile.close();
    }

    // Read worker-side inference telemetry written by the Python receiver
    double latencyP99Ms = 0.0;
    double errorRate = 0.0;
    int inferenceCount = 0;
    ifstream telemetryFile("/tmp/worker_telemetry.json");
    if (telemetryFile.good()) {
        string telemetry((istreambuf_iterator<char>(telemetryFile)), istreambuf_iterator<char>());
        telemetryFile.close();

        auto readNumber = [&](const string& key) -> double {
            size_t pos = telemetry.find("\"" + key + "\":");
            if (pos == string::npos) return 0.0;
            pos = telemetry.find(':', pos) + 1;
            while (pos < telemetry.size() && (telemetry[pos] == ' ' || telemetry[pos] == '\"')) pos++;
            return atof(telemetry.c_str() + pos);
        };

        latencyP99Ms = readNumber("inference_latency_p99_ms");
        errorRate = readNumber("error_rate");
        inferenceCount = static_cast<int>(readNumber("inference_count"));
    }

    stringstream ss;
    ss << "{\"cpu\": " << cpuLoad
       << ", \"ram\": " << ramUsage
       << ", \"temperature_c\": " << tempC
       << ", \"inference_latency_p99_ms\": " << latencyP99Ms
       << ", \"error_rate\": " << errorRate
       << ", \"inference_count\": " << inferenceCount
       << ", \"timestamp\": \"" << time(0) << "\"}";
    return ss.str();
}

int main(int argc, char* argv[]) {
    int port = (argc > 1) ? atoi(argv[1]) : 8080;
    unsigned int seed = static_cast<unsigned int>(time(0) + port + getpid());

    if (argc > 2 && argv[2][0] != '\0') {
        unsigned int nodeHash = hashNodeId(argv[2]);
        seed += nodeHash;
        node_cpu_bias = nodeHash % 25;
        node_ram_bias = (nodeHash >> 4) % 20;
        node_temp_bias = (nodeHash >> 8) % 8;
    }

    srand(seed);

    // Create TCP socket
    int server_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (server_fd < 0) {
        cerr << "[ERROR] Failed to create socket" << endl;
        return 1;
    }

    // Allow socket reuse
    int opt = 1;
    setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    struct sockaddr_in address;
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = INADDR_ANY;  // Listen on all interfaces
    address.sin_port = htons(port);

    // Bind socket
    if (bind(server_fd, (struct sockaddr*)&address, sizeof(address)) < 0) {
        cerr << "[ERROR] Failed to bind socket on port " << port << endl;
        return 1;
    }

    // Listen for connections
    listen(server_fd, 10);
    const char* nodeLabel = (argc > 2 && argv[2][0] != '\0') ? argv[2] : "default";
    cout << "[SENTINEL NODE ACTIVE] " << nodeLabel << " listening on port " << port << " | PID: " << getpid() << endl;

    // Handle incoming health check requests
    while (true) {
        int new_socket = accept(server_fd, NULL, NULL);
        if (new_socket >= 0) {
            char buffer[1024] = {0};
            read(new_socket, buffer, sizeof(buffer));

            // Parse HTTP request
            string request(buffer);
            if (request.find("GET /health") != string::npos || request.find("GET /") != string::npos) {
                string metrics = getMetrics(port);
                string response = "HTTP/1.1 200 OK\r\n"
                                  "Content-Type: application/json\r\n"
                                  "Access-Control-Allow-Origin: *\r\n"
                                  "Content-Length: " + to_string(metrics.length()) + "\r\n"
                                  "Connection: close\r\n\r\n" + metrics;

                write(new_socket, response.c_str(), response.length());
            }
            close(new_socket);
        }
    }
    close(server_fd);
    return 0;
}