#!/bin/bash
set -euo pipefail

echo "=== Testing Failover Alert ==="

# Initial state
echo "1. Initial state:"
curl -s http://localhost:8080/version | grep -E "(X-App-Pool|X-Release-Id)" || echo "No headers"

echo -e "\n2. Starting chaos on blue pool (simulating failure)..."
curl -s -X POST "http://localhost:8081/chaos/start?mode=error"

echo -e "\n3. Generating traffic to trigger failover..."
for i in {1..30}; do
    response=$(curl -s -w " %{http_code}" http://localhost:8080/version 2>/dev/null || echo "failed")
    echo "Request $i: $response"
    sleep 0.5
done

echo -e "\n4. Checking current pool (should be green now)..."
curl -s http://localhost:8080/version | grep -E "(X-App-Pool|X-Release-Id)" || echo "No headers"

echo -e "\n5. Stopping chaos..."
curl -s -X POST "http://localhost:8081/chaos/stop"

echo -e "\n6. Waiting for recovery..."
sleep 10

echo -e "\n7. Final state:"
curl -s http://localhost:8080/version | grep -E "(X-App-Pool|X-Release-Id)" || echo "No headers"

echo -e "\n✅ Failover test completed! Check Slack for alerts."