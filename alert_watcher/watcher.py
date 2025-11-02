#!/usr/bin/env python3
import os
import time
import re
from collections import deque
from slack_sdk.webhook import WebhookClient
from datetime import datetime

class LogWatcher:
    def __init__(self):
        self.slack_webhook = os.getenv('SLACK_WEBHOOK_URL')
        self.error_threshold = float(os.getenv('ERROR_RATE_THRESHOLD', 2))
        self.window_size = int(os.getenv('WINDOW_SIZE', 200))
        self.cooldown_sec = int(os.getenv('ALERT_COOLDOWN_SEC', 300))
        self.maintenance_mode = os.getenv('MAINTENANCE_MODE', 'false').lower() == 'true'
        
        self.request_window = deque(maxlen=self.window_size)
        self.last_alert_time = {}
        self.current_pool = os.getenv('INITIAL_ACTIVE_POOL', 'blue')
        self.last_seen_pool = self.current_pool
        
        self.slack_client = WebhookClient(self.slack_webhook) if self.slack_webhook else None
        
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
        """Parse a log line and extract relevant fields"""
        match = self.log_pattern.match(line)
        if match:
            return match.groupdict()
        return None
    
    def calculate_error_rate(self):
        """Calculate current error rate in the window"""
        if not self.request_window:
            return 0.0
        
        error_count = sum(1 for req in self.request_window 
                         if req.get('upstream_status', '').startswith('5'))
        return (error_count / len(self.request_window)) * 100
    
    def should_alert(self, alert_type):
        """Check if we should send an alert based on cooldown"""
        now = time.time()
        last_time = self.last_alert_time.get(alert_type, 0)
        return (now - last_time) >= self.cooldown_sec
    
    def send_slack_alert(self, message, alert_type):
        """Send alert to Slack"""
        if self.maintenance_mode:
            print(f"MAINTENANCE MODE: Suppressing alert: {message}")
            return
        
        if not self.slack_client:
            print(f"SLACK ALERT (no webhook): {message}")
            return
        
        if not self.should_alert(alert_type):
            print(f"COOLDOWN: Suppressing {alert_type} alert: {message}")
            return
        
        try:
            response = self.slack_client.send(
                text=message,
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"🚨 *Deployment Alert*\n{message}"
                        }
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": f"Environment: {os.getenv('ENVIRONMENT', 'unknown')} | Time: {datetime.now().isoformat()}"
                            }
                        ]
                    }
                ]
            )
            if response.status_code == 200:
                self.last_alert_time[alert_type] = time.time()
                print(f"Alert sent: {message}")
            else:
                print(f"Failed to send alert: {response.body}")
        except Exception as e:
            print(f"Error sending Slack alert: {e}")
    
    def detect_failover(self, pool):
        """Detect and alert on failover events"""
        if pool and pool != self.last_seen_pool:
            message = f"Failover detected: {self.last_seen_pool.upper()} → {pool.upper()}"
            self.send_slack_alert(message, 'failover')
            self.last_seen_pool = pool
    
    def monitor_error_rate(self, log_data):
        """Monitor and alert on error rates"""
        if log_data.get('upstream_status'):
            self.request_window.append(log_data)
            error_rate = self.calculate_error_rate()
            
            if error_rate > self.error_threshold:
                message = (f"High error rate detected: {error_rate:.1f}% "
                          f"(threshold: {self.error_threshold}% over last {self.window_size} requests)")
                self.send_slack_alert(message, 'error_rate')
    
    def process_log_line(self, line):
        """Process a single log line"""
        log_data = self.parse_log_line(line)
        if not log_data:
            return
        
        pool = log_data.get('pool')
        
        # Detect failovers
        self.detect_failover(pool)
        
        # Monitor error rates
        self.monitor_error_rate(log_data)
        
        # Update current pool for tracking
        if pool:
            self.current_pool = pool
    
    def watch_logs(self):
        """Main loop to watch and process logs"""
        log_file = '/var/log/nginx/access.log'
        
        print(f"Starting log watcher with config:")
        print(f"  Error threshold: {self.error_threshold}%")
        print(f"  Window size: {self.window_size} requests")
        print(f"  Cooldown: {self.cooldown_sec} seconds")
        print(f"  Maintenance mode: {self.maintenance_mode}")
        print(f"  Initial pool: {self.current_pool}")
        
        # Wait for log file to be created
        while not os.path.exists(log_file):
            print(f"Waiting for log file: {log_file}")
            time.sleep(2)
        
        print(f"Monitoring log file: {log_file}")
        
        # Tail the log file
        with open(log_file, 'r') as f:
            # Go to end of file
            f.seek(0, 2)
            
            while True:
                line = f.readline()
                if line:
                    self.process_log_line(line.strip())
                else:
                    time.sleep(0.1)

if __name__ == '__main__':
    watcher = LogWatcher()
    watcher.watch_logs()