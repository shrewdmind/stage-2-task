#!/bin/bash
set -euo pipefail

echo "=== TESTING BOTH ALERTS: High Error Rate AND Failover ==="

# Monitor alert watcher
echo "📊 Starting alert watcher monitoring..."
docker compose logs -f alert_watcher &
LOG_PID=$!

cleanup() {
    echo "🧹 Cleaning up..."
    kill $LOG_PID 2>/dev/null
    curl -s -X POST "http://localhost:8081/chaos/stop" > /dev/null
}
trap cleanup EXIT INT TERM

sleep 3

echo ""
echo "🎯 PHASE 1: Testing High Error Rate Alert"
echo "🔴 Starting chaos to generate 5xx errors..."
curl -s -X POST "http://localhost:8081/chaos/start?mode=error"
echo "   Chaos started at: $(date)"

echo "📈 Generating 150 requests to trigger error rate alert..."
for i in {1..150}; do
    curl -s "http://localhost:8080/version?error_test=$i" > /dev/null
    if (( i % 25 == 0 )); then
        echo "   Progress: $i/150 requests"
        # Check current pool
        pool=$(curl -s -I "http://localhost:8080/version" | grep -i "X-App-Pool" | cut -d: -f2 | tr -d ' \r' || echo "unknown")
        echo "   Current pool: $pool"
    fi
    sleep 0.1
done

echo "⏳ Waiting 10 seconds for error rate alert..."
sleep 10

echo ""
echo "🎯 PHASE 2: Testing Failover Alert" 
echo "📈 Generating more requests to trigger failover..."
for i in {1..50}; do
    curl -s "http://localhost:8080/version?failover_test=$i" > /dev/null
    sleep 0.2
done

echo "🟢 Stopping chaos..."
curl -s -X POST "http://localhost:8081/chaos/stop"

echo "⏳ Waiting 15 seconds for final alerts..."
sleep 15

echo ""
echo "✅ TEST COMPLETE!"
echo "📋 Expected Slack alerts:"
echo "   1. 🚨 High Error Rate Detected"
echo "   2. ⚠️ Failover Detected"
echo ""
echo "Check your Slack channel for both alerts!"