#!/bin/bash
set -euo pipefail

echo "=== TESTING ALL THREE ALERTS ==="
echo "🎯 Testing: High Error Rate → Failover → Service Recovery"

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
echo "🔴 PHASE 1: Testing High Error Rate Alert"
echo "   Starting chaos to generate 5xx errors..."
curl -s -X POST "http://localhost:8081/chaos/start?mode=error"
echo "   Chaos started at: $(date)"

echo "📈 Generating requests to trigger error rate alert..."
for i in {1..120}; do
    curl -s "http://localhost:8080/version?phase1_error=$i" > /dev/null
    if (( i % 30 == 0 )); then
        echo "   Progress: $i/120 requests"
    fi
    sleep 0.1
done

echo "⏳ Waiting for error rate alert..."
sleep 10

echo ""
echo "🔄 PHASE 2: Testing Failover Alert" 
echo "📈 Generating more requests to trigger failover..."
for i in {1..80}; do
    curl -s "http://localhost:8080/version?phase2_failover=$i" > /dev/null
    if (( i % 20 == 0 )); then
        pool=$(curl -s -I "http://localhost:8080/version" | grep -i "X-App-Pool" | cut -d: -f2 | tr -d ' \r' || echo "unknown")
        echo "   Current pool: $pool"
    fi
    sleep 0.2
done

echo "⏳ Waiting for failover alert..."
sleep 10

echo ""
echo "🟢 PHASE 3: Testing Service Recovery Alert"
echo "   Stopping chaos to allow recovery..."
curl -s -X POST "http://localhost:8081/chaos/stop"
echo "   Chaos stopped at: $(date)"

echo "   Waiting for primary pool to recover..."
sleep 15

echo "📈 Generating successful requests to confirm recovery..."
for i in {1..50}; do
    curl -s "http://localhost:8080/version?phase3_recovery=$i" > /dev/null
    if (( i % 10 == 0 )); then
        pool=$(curl -s -I "http://localhost:8080/version" | grep -i "X-App-Pool" | cut -d: -f2 | tr -d ' \r' || echo "unknown")
        echo "   Current pool: $pool"
    fi
    sleep 0.3
done

echo "⏳ Waiting for service recovery alert..."
sleep 10

echo ""
echo "✅ TEST COMPLETE!"
echo "📋 Expected Slack alerts in this order:"
echo "   1. 🚨 High Error Rate Detected"
echo "   2. ⚠️ Failover Detected" 
echo "   3. ✅ Service Recovery"
echo ""
echo "Check your Slack channel for all three alerts!"