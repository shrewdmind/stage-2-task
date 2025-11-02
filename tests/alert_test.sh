#!/bin/bash
set -euo pipefail

echo "Testing alert system..."

# Test 1: Generate enough errors to trigger error rate alert
echo "Generating errors to test error rate alert..."
for i in {1..50}; do
    curl -s http://localhost:8081/chaos/start?mode=error > /dev/null &
done
wait

# Make some requests through nginx to generate errors
echo "Making requests through nginx..."
for i in {1..100}; do
    curl -s http://localhost:8080/version > /dev/null || true
    sleep 0.1
done

# Test 2: Trigger failover alert
echo "Triggering failover..."
bash tests/induce_chaos.sh start
sleep 5

# Make requests to ensure failover
for i in {1..20}; do
    curl -s http://localhost:8080/version > /dev/null || true
    sleep 0.2
done

# Clean up
bash tests/induce_chaos.sh stop

echo "Alert test completed. Check Slack for alerts."