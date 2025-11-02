#!/bin/bash
set -euo pipefail

echo "=== Testing Error Rate Alert ==="

echo "1. Starting chaos to generate 5xx errors..."
curl -s -X POST "http://localhost:8081/chaos/start?mode=error"

echo -e "\n2. Generating high volume of requests to trigger error rate alert..."
for i in {1..150}; do
    curl -s "http://localhost:8080/version?request=$i" > /dev/null &
    # Run 10 concurrent requests to speed up
    if (( i % 10 == 0 )); then
        wait
        echo "Generated $i requests..."
    fi
done
wait

echo -e "\n3. Generating more requests to ensure window is filled..."
for i in {1..50}; do
    curl -s "http://localhost:8080/version?batch2=$i" > /dev/null
    sleep 0.1
done

echo -e "\n4. Stopping chaos..."
curl -s -X POST "http://localhost:8081/chaos/stop"

echo -e "\n5. Generating successful requests to test recovery alert..."
for i in {1..50}; do
    curl -s "http://localhost:8080/version?recovery=$i" > /dev/null
    sleep 0.2
done

echo -e "\n✅ Error rate test completed! Check Slack for error rate and recovery alerts."