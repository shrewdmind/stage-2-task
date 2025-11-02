# Deployment Alerts Runbook

## Alert Types and Responses

### 🚨 High Error Rate Detected
**What happened**: >2% of last 200 requests returned 5xx errors
**Immediate Actions**:
1. Check which pool is currently active
2. Review application logs for the failing pool  
3. Check database connections and external dependencies
4. Verify resource utilization (CPU, Memory, Disk)
**Follow-up**: Consider rollback if error started after deployment

### ⚠️ Failover Detected
**What happened**: Traffic automatically switched from primary to backup pool
**Immediate Actions**:
1. Identify why primary pool failed - check container health
2. Verify failover was successful - check backup pool performance
3. Monitor backup pool for any issues
4. Document the incident timeline
**Follow-up**: Plan primary pool restoration

### ✅ Service Recovery  
**What happened**: Traffic returned to primary pool after failover
**Immediate Actions**:
1. Verify primary pool is healthy and responding
2. Check that all services are functioning normally
3. Monitor for any residual issues or error rates
4. Update incident documentation
**Follow-up**: Analyze root cause of original failure

### 🟢 Error Rate Recovery
**What happened**: 5xx error rate returned to normal levels
**Immediate Actions**:
1. Confirm error rate is stable and below threshold
2. Check if automatic recovery occurred or intervention was needed
3. Verify all services are operating normally
**Follow-up**: Document resolution for future reference

**Immediate Actions**:
1. Check primary pool health:
   ```bash
   docker compose ps app_blue app_green
   docker compose logs app_blue  # if blue was primary
   ```
2. Verify backup pool is handling traffic:
    ```
    bash
    curl -s http://localhost:8080/version | grep X-App-Pool
    ```
3. Check for resource issues:
    ```
    bash
    docker stats app_blue app_green
    ```

**Follow-up Actions**:
- Investigate why primary pool failed
- Consider rolling back if this was a deployment issue
- Plan primary pool restoration

### 2. High Error Rate
**Message**: "High error rate detected: X.X% (threshold: 2% over last 200 requests)"

**What it means**:
- More than 2% of requests are returning 5xx errors
- This could indicate application issues or infrastructure problems

**Immediate Actions**:
1. Check current error rate:
    ```
    bash
    tail -100 /var/log/nginx/access.log | grep 'upstream_status=5'
    ```
2. Identify patterns in errors:
    ```
    bash
    tail -200 /var/log/nginx/access.log | awk '{print $8}' | sort | uniq -c
    ```
3. Check application logs:
    ```
    bash
    docker compose logs app_blue --tail=50
    docker compose logs app_green --tail=50
    ```

**Follow-up Actions**:
- Scale resources if needed
- Roll back deployment if recent
- Implement fixes for identified issues

## Maintenance Mode
To suppress alerts during planned maintenance:

1. Set maintenance mode in .env:
    ```
    bash
    MAINTENANCE_MODE=true
    ```
2. Recreate alert watcher:
    ```
    bash
    docker compose up -d --force-recreate alert_watcher
    ```

## Manual Pool Switching
1. Update .env with new active pool
2. Recreate nginx:
    ```
    bash
    docker compose up -d --force-recreate nginx
    ```
3. The watcher will detect this as a failover but won't alert in maintenance mode

## Recovery Procedures

### Primary Pool Recovery
1. Fix issues in primary pool
2. Stop chaos if active: bash tests/induce_chaos.sh stop
3. Switch back to primary pool in .env
4. Recreate nginx container

### Monitoring Recovery
- Check alert watcher logs: docker compose logs alert_watcher
- Verify nginx logs: docker compose logs nginx
- Test failover: bash tests/failover_test.sh

## Troubleshooting

### No Alerts Being Sent
1. Check Slack webhook URL in .env
2. Verify alert_watcher is running: docker compose ps alert_watcher
3, Check watcher logs: docker compose logs alert_watcher

### Too Many Alerts
1. Increase cooldown period in .env
2. Adjust error threshold if needed
3. Enable maintenance mode for planned changes

### Log Parsing Issues
- Verify nginx log format matches watcher expectations
- Check log file permissions
- Restart both nginx and alert_watcher

## 11. Usage Instructions

### Setup and Test

1. **Update your .env** with the new variables
2. **Build and start the stack**:
   ```bash
   docker compose up -d --build
   ```
3. Test the alert system:
    ```
    bash
    bash tests/alert_test.sh
    ```
4. Verify alerts in your Slack channel

### Manual Testing
    ```
    bash
    # Test error rate alert
    for i in {1..150}; do curl -s http://localhost:8080/version > /dev/null & done
    wait

    # Test failover alert
    bash tests/induce_chaos.sh start
    sleep 3
    curl -s http://localhost:8080/version
    bash tests/induce_chaos.sh stop
    ```
### Maintenance Mode
    ```
    bash
    # Enable maintenance mode
    export MAINTENANCE_MODE=true
    docker compose up -d --force-recreate alert_watcher

    # Perform maintenance tasks...

    # Disable maintenance mode
    export MAINTENANCE_MODE=false
    docker compose up -d --force-recreate alert_watcher
    ```

### This implementation provides:

- ✅ Enhanced Nginx logging with pool and release information
- ✅ Real-time log monitoring with Python watcher
- ✅ Slack alerts for failovers and error rates
- ✅ Configurable thresholds and cooldowns
- ✅ Maintenance mode for planned changes
- ✅ Comprehensive runbook for operators
- ✅ Zero modifications to application images
- ✅ Shared log volume between services
