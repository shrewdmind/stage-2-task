#!/usr/bin/env python3
import os
import time
import re
from collections import deque
from slack_sdk.webhook import WebhookClient
from datetime import datetime

class LogWatcher:
    def __init__(self):
        # Environment variables from .env
        self.slack_webhook = os.getenv('SLACK_WEBHOOK_URL')
        self.error_threshold = float(os.getenv('ERROR_RATE_THRESHOLD', 2))
        self.window_size = int(os.getenv('WINDOW_SIZE', 200))
        self.cooldown_sec = int(os.getenv('ALERT_COOLDOWN_SEC', 300))
        self.maintenance_mode = os.getenv('MAINTENANCE_MODE', 'false').lower() == 'true'
        
        # Alert state tracking
        self.request_window = deque(maxlen=self.window_size)
        self.last_alert_time = {}
        self.current_pool = os.getenv('INITIAL_ACTIVE_POOL', 'blue')
        self.last_seen_pool = self.current_pool
        self.initial_pool = self.current_pool  # Track original pool for recovery
        self.error_alert_sent = False
        self.failover_occurred = False
        
        # Initialize Slack client
        if self.slack_webhook:
            self.slack_client = WebhookClient(self.slack_webhook)
            print("✅ Slack client initialized")
        else:
            self.slack_client = None
            print("❌ SLACK_WEBHOOK_URL not set")
        
        # Log parsing pattern - captures all required fields
        self.log_pattern = re.compile(
            r'\[(?P<timestamp>[^\]]+)\] (?P<remote_addr>\S+) "(?P<request>[^"]*)" (?P<status>\d+) '
            r'pool="(?P<pool>[^"]*)" '
            r'release="(?P<release>[^"]*)" '
            r'upstream_status=(?P<upstream_status>\d+|-) '
            r'upstream_addr=(?P<upstream_addr>\S+) '
            r'request_time=(?P<request_time>[\d.]+) '
            r'upstream_response_time=(?P<upstream_response_time>[\d.-]+)'
        )
    
    def parse_log_line(self, line):
        """Parse log line to extract all required fields"""
        match = self.log_pattern.match(line)
        if match:
            return match.groupdict()
        return None
    
    def calculate_error_rate(self):
        """Calculate 5xx error rate over sliding window"""
        if len(self.request_window) == 0:
            return 0.0
        
        error_count = sum(1 for req in self.request_window 
                         if req.get('upstream_status', '').startswith('5'))
        return (error_count / len(self.request_window)) * 100
    
    def should_alert(self, alert_type):
        """Enforce alert cooldowns to prevent spam"""
        now = time.time()
        last_time = self.last_alert_time.get(alert_type, 0)
        return (now - last_time) >= self.cooldown_sec
    
    def send_slack_alert(self, message, alert_type):
        """Post alert to Slack webhook"""
        if self.maintenance_mode:
            print(f"🔧 MAINTENANCE: Suppressed {alert_type}")
            return False
            
        if not self.slack_client:
            print(f"❌ No Slack client for {alert_type}")
            return False
            
        if not self.should_alert(alert_type):
            print(f"⏰ Cooldown active for {alert_type}")
            return False
        
        try:
            response = self.slack_client.send(text=message)
            if response.status_code == 200:
                self.last_alert_time[alert_type] = time.time()
                print(f"✅ {alert_type.upper()} sent to Slack")
                return True
            else:
                print(f"❌ Slack error: {response.body}")
                return False
        except Exception as e:
            print(f"💥 Slack send failed: {e}")
            return False
    
    def detect_failover(self, pool):
        """Detect Blue→Green or Green→Blue failover"""
        if pool and pool != self.last_seen_pool:
            print(f"🔄 FAILOVER: {self.last_seen_pool.upper()} → {pool.upper()}")
            
            message = (f"⚠️ *Failover Detected*\n"
                      f"Traffic switched from {self.last_seen_pool.upper()} to {pool.upper()} pool\n"
                      f"• Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
                      f"• Action: Check health of {self.last_seen_pool.upper()} container")
            
            if self.send_slack_alert(message, 'failover'):
                self.last_seen_pool = pool
                self.failover_occurred = True
    
    def detect_service_recovery(self, pool):
        """Detect when service returns to primary pool"""
        if (self.failover_occurred and 
            pool == self.initial_pool and 
            pool != self.last_seen_pool):
            
            print(f"🟢 SERVICE RECOVERY: Back to {pool.upper()} pool")
            
            message = (f"✅ *Service Recovery*\n"
                      f"Primary {pool.upper()} pool is serving traffic again\n"
                      f"• Recovery Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
                      f"• Status: Primary pool restored and healthy")
            
            if self.send_slack_alert(message, 'recovery'):
                self.failover_occurred = False
    
    def monitor_error_rate(self, log_data):
        """Monitor >2% 5xx error rate over last 200 requests"""
        if log_data.get('upstream_status'):
            self.request_window.append(log_data)
            
            current_size = len(self.request_window)
            error_rate = self.calculate_error_rate()
            error_count = sum(1 for req in self.request_window 
                             if req.get('upstream_status', '').startswith('5'))
            
            # Show progress for debugging
            if current_size % 25 == 0:
                print(f"📈 Error Rate: {error_rate:.1f}% ({error_count}/{current_size})")
            
            # Check threshold with minimum samples to avoid false positives
            if current_size >= 50 and error_rate > self.error_threshold and not self.error_alert_sent:
                print(f"🚨 HIGH ERROR RATE: {error_rate:.1f}% > {self.error_threshold}%")
                
                message = (f"🚨 *High Error Rate Detected*\n"
                          f"Upstream 5xx errors exceed {self.error_threshold}% threshold\n"
                          f"• Current Rate: {error_rate:.1f}%\n"
                          f"• Errors: {error_count}/{current_size} requests\n"
                          f"• Window: Last {self.window_size} requests\n"
                          f"• Pool: {self.current_pool.upper()}\n"
                          f"• Time: {datetime.now().isoformat()}\n"
                          f"• Action: Inspect upstream logs, consider pool toggle")
                
                if self.send_slack_alert(message, 'error_rate'):
                    self.error_alert_sent = True
            
            # Reset when errors drop and send recovery alert
            elif error_rate <= 1.0 and self.error_alert_sent:  # Use 1% as recovery threshold
                print("📉 Error rate returned to normal levels")
                recovery_message = (f"🟢 *Error Rate Recovery*\n"
                                  f"5xx error rate returned to normal: {error_rate:.1f}%\n"
                                  f"• Recovery Time: {datetime.now().isoformat()}\n"
                                  f"• Status: Error rate stabilized")
                self.send_slack_alert(recovery_message, 'error_recovery')
                self.error_alert_sent = False
    
    def process_log_line(self, line):
        """Process each nginx log line"""
        log_data = self.parse_log_line(line)
        if not log_data:
            return
        
        pool = log_data.get('pool')
        
        # Update pool and detect failovers/recovery
        if pool:
            old_pool = self.current_pool
            self.current_pool = pool
            
            # Detect failover to backup pool
            if pool != old_pool:
                self.detect_failover(pool)
            
            # Detect recovery back to primary pool
            self.detect_service_recovery(pool)
        
        # Monitor error rates
        self.monitor_error_rate(log_data)
    
    def watch_logs(self):
        """Tail nginx logs in real time"""
        log_file = '/var/log/nginx/access.log'
        
        print(f"📁 Monitoring: {log_file}")
        print("🎯 Detecting: Failovers, High Error Rates, Service Recovery")
        
        # Wait for log file
        while not os.path.exists(log_file):
            print("⏳ Waiting for nginx logs...")
            time.sleep(2)
        
        # Track file position
        last_size = 0
        
        while True:
            try:
                current_size = os.path.getsize(log_file)
                
                if current_size > last_size:
                    with open(log_file, 'r') as f:
                        f.seek(last_size)
                        new_lines = f.readlines()
                        last_size = current_size
                    
                    for line in new_lines:
                        self.process_log_line(line.strip())
                
                time.sleep(0.5)
                
            except Exception as e:
                print(f"❌ Log error: {e}")
                time.sleep(2)

if __name__ == '__main__':
    watcher = LogWatcher()
    watcher.watch_logs()