#!/bin/bash
set -euo pipefail

echo "=== Quick High Error Rate Alert Test ==="

echo "🔴 Starting chaos on blue pool..."
curl -s -X POST "http://localhost:8081/chaos/start?mode=error"

echo "📈 Generating 250 requests quickly to trigger error rate alert..."
# Use parallel requests to generate errors quickly
for i in {1..5}; do
    echo "  Batch $i: 50 requests..."
    for j in {1..50}; do
        curl -s "http://localhost:8080/version?batch=${i}&req=${j}" > /dev/null &
    done
    wait
    sleep 1
done

echo "📊 Current error rate window should be filled with errors..."
echo "🟢 Stopping chaos..."
curl -s -X POST "http://localhost:8081/chaos/stop"

echo "🔄 Generating successful requests to test recovery..."
for i in {1..50}; do
    curl -s "http://localhost:8080/version?recovery=${i}" > /dev/null
    sleep 0.1
done

echo "✅ Quick test completed! Check Slack for High Error Rate Alert."