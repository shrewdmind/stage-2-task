#!/bin/bash
set -euo pipefail

echo "=== Comprehensive Alert Test Scenario ==="

echo "📋 This test will simulate:"
echo "  1. Normal operation"
echo "  2. High error rate triggering alert"
echo "  3. Failover to backup pool"
echo "  4. Recovery back to primary pool"
echo "  5. Service recovery alert"

sleep 3

# Phase 1: Normal operation
echo -e "\n🎯 Phase 1: Normal operation (30 seconds)"
for i in {1..30}; do
    curl -s "http://localhost:8080/version?phase=normal&req=$i" > /dev/null
    sleep 1
done

# Phase 2: High error rate
echo -e "\n🔴 Phase 2: Generating high error rate (60 seconds)"
curl -s -X POST "http://localhost:8081/chaos/start?mode=error"

for i in {1..60}; do
    curl -s "http://localhost:8080/version?phase=errors&req=$i" > /dev/null
    sleep 1
done

# Phase 3: Failover should occur here
echo -e "\n🔄 Phase 3: Failover detection (30 seconds)"
for i in {1..30}; do
    curl -s "http://localhost:8080/version?phase=failover&req=$i" > /dev/null
    sleep 1
done

# Phase 4: Recovery
echo -e "\n🟢 Phase 4: Recovery (30 seconds)"
curl -s -X POST "http://localhost:8081/chaos/stop"
sleep 10  # Wait for primary to recover

for i in {1..30}; do
    curl -s "http://localhost:8080/version?phase=recovery&req=$i" > /dev/null
    sleep 1
done

echo -e "\n✅ Comprehensive test completed!"
echo "Expected alerts in Slack:"
echo "  🔴 High Error Rate Alert"
echo "  ⚠️  Failover Alert" 
echo "  ✅ Service Recovery Alert"
echo "  🟢 Error Rate Recovery Alert"