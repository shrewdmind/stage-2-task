#!/usr/bin/env python3
import os
import time
import re
from collections import deque
from slack_sdk.webhook import WebhookClient
from datetime import datetime

class LogWatcher:
    def __init__(self):
        # Environment variables for configuration
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
        self.error_alert_sent = False
        
        # Initialize Slack client PROPERLY
        if self.slack_webhook:
            self.slack_client = WebhookClient(self.slack_webhook)
            print(f"✅ Slack client initialized with webhook")
        else:
            self.slack_client = None
            print("❌ SLACK_WEBHOOK_URL not set - alerts will be logged only")
        
        # Log patterns for parsing
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
        """Parse log line to extract: pool, release, upstream_status, latency, upstream_addr"""
        match = self.log_pattern.match(line)
        if match:
            data = match.groupdict()
            # Debug: Show we're capturing all required fields
            if len(self.request_window) % 50 == 0:  # Log every 50th request
                print(f"📝 Log parsed: pool={data.get('pool')}, upstream_status={data.get('upstream_status')}, "
                      f"request_time={data.get('request_time')}, upstream_addr={data.get('upstream_addr')}")
            return data
        return None
    
    def calculate_error_rate(self):
        """Calculate 5xx error rate over sliding window"""
        if len(self.request_window) < 10:  # Minimum samples
            return 0.0
        
        error_count = sum(1 for req in self.request_window 
                         if req.get('upstream_status', '').startswith('5'))
        error_rate = (error_count / len(self.request_window)) * 100
        
        # Show error rate progress
        if len(self.request_window) % 25 == 0:
            print(f"📊 Error Rate: {error_rate:.1f}% ({error_count}/{len(self.request_window)} requests)")
        
        return error_rate
    
    def should_alert(self, alert_type):
        """Enforce alert cooldown periods using environment variable"""
        now = time.time()
        last_time = self.last_alert_time.get(alert_type, 0)
        can_alert = (now - last_time) >= self.cooldown_sec
        
        if not can_alert:
            remaining = int(self.cooldown_sec - (now - last_time))
            print(f"⏰ Cooldown active for {alert_type}: {remaining}s remaining")
        
        return can_alert
    
    def send_slack_alert(self, message, alert_type):
        """Post formatted alert to Slack using official SDK"""
        if self.maintenance_mode:
            print(f"🔧 MAINTENANCE MODE: Suppressed {alert_type} alert")
            return False
            
        if not self.slack_client:
            print(f"❌ Slack client not initialized - cannot send {alert_type} alert")
            return False
            
        if not self.should_alert(alert_type):
            print(f"⏰ Cooldown active for {alert_type} alert")
            return False
        
        try:
            print(f"📤 Sending {alert_type} alert to Slack...")
            
            # Use the proper Slack SDK method
            response = self.slack_client.send(
                text=message,
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": message
                        }
                    }
                ]
            )
            
            # Proper error handling with Slack SDK
            if response.status_code == 200:
                self.last_alert_time[alert_type] = time.time()
                print(f"✅ {alert_type.upper()} alert sent successfully to Slack")
                return True
            else:
                print(f"❌ Slack API error: {response.status_code} - {response.body}")
                return False
                
        except Exception as e:
            print(f"💥 Error sending Slack alert: {str(e)}")
            return False
    
    def detect_failover(self, pool):
        """Detect and alert on Blue→Green or Green→Blue failover events"""
        if pool and pool != self.last_seen_pool:
            print(f"🔄 FAILOVER DETECTED: {self.last_seen_pool.upper()} → {pool.upper()}")
            
            message = (f"⚠️ *Failover Event Detected*\n"
                      f"Traffic automatically switched pools:\n"
                      f"• From: *{self.last_seen_pool.upper()}* pool\n"  
                      f"• To: *{pool.upper()}* pool\n"
                      f"• Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
                      f"• Window: {self.window_size} requests")
            
            if self.send_slack_alert(message, 'failover'):
                self.last_seen_pool = pool
            else:
                print("❌ Failed to send failover alert")
    
    def monitor_error_rates(self, log_data):
        """Monitor elevated upstream 5xx error rates over sliding window"""
        if log_data.get('upstream_status'):
            self.request_window.append(log_data)
            
            current_size = len(self.request_window)
            error_rate = self.calculate_error_rate()
            error_count = sum(1 for req in self.request_window 
                             if req.get('upstream_status', '').startswith('5'))
            
            # Check if error rate exceeds threshold (with minimum samples)
            if current_size >= 50 and error_rate > self.error_threshold and not self.error_alert_sent:
                print(f"🚨 HIGH ERROR RATE: {error_rate:.1f}% > {self.error_threshold}% threshold")
                
                message = (f"🚨 *High Error Rate Detected*\n"
                          f"Upstream 5xx errors exceed configured threshold:\n"
                          f"• Current Rate: `{error_rate:.1f}%`\n"
                          f"• Threshold: `{self.error_threshold}%`\n" 
                          f"• Errors: `{error_count}/{current_size}` requests\n"
                          f"• Window: Last `{self.window_size}` requests\n"
                          f"• Pool: `{self.current_pool.upper()}`\n"
                          f"• Time: `{datetime.now().isoformat()}`")
                
                if self.send_slack_alert(message, 'error_rate'):
                    self.error_alert_sent = True
                else:
                    print("❌ Failed to send error rate alert")
            
            # Reset alert flag when error rate drops
            elif error_rate <= self.error_threshold and self.error_alert_sent:
                print("📉 Error rate returned to normal levels")
                self.error_alert_sent = False
    
    def process_log_line(self, line):
        """Process each nginx log line for alert detection"""
        log_data = self.parse_log_line(line)
        if not log_data:
            return
        
        pool = log_data.get('pool')
        
        # Update current pool and detect failovers
        if pool:
            if pool != self.current_pool:
                old_pool = self.current_pool
                self.current_pool = pool
                self.detect_failover(pool)
        
        # Monitor error rates (primary detection)
        self.monitor_error_rates(log_data)
    
    def watch_logs(self):
        """Tail nginx logs and process in real-time"""
        log_file = '/var/log/nginx/access.log'
        
        print(f"📁 Monitoring nginx logs: {log_file}")
        print("🎯 Ready to detect: Failover events & High error rates")
        print("🔧 Using official Slack SDK for webhook integration")
        print("=" * 60)
        
        # Wait for log file
        while not os.path.exists(log_file):
            print(f"⏳ Waiting for nginx log file...")
            time.sleep(2)
        
        # Efficient file tailing
        last_size = 0
        
        while True:
            try:
                current_size = os.path.getsize(log_file)
                
                if current_size > last_size:
                    with open(log_file, 'r') as f:
                        f.seek(last_size)
                        new_lines = f.readlines()
                        last_size = f.tell()
                    
                    print(f"📨 Processing {len(new_lines)} new log lines...")
                    
                    for line in new_lines:
                        self.process_log_line(line.strip())
                
                time.sleep(1)  # Check every second
                
            except Exception as e:
                print(f"❌ Log reading error: {e}, retrying...")
                time.sleep(2)

if __name__ == '__main__':
    watcher = LogWatcher()
    watcher.watch_logs()