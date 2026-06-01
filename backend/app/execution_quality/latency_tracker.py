from datetime import datetime
from typing import Dict


class LatencyTracker:
    @staticmethod
    def calculate_latencies(
        signal_time: datetime,
        submission_time: datetime,
        ack_time: datetime,
        fill_time: datetime
    ) -> Dict[str, int]:
        """
        Calculates differences in milliseconds between execution milestones:
        - signal_to_submit: time taken to approve and prepare the order.
        - submit_to_ack: network + exchange acknowledgment latency.
        - ack_to_fill: exchange matching engine execution latency.
        - total_delay: total execution turnaround time.
        """
        # Ensure correct datetime ordering
        sig_to_sub = max(0, int((submission_time - signal_time).total_seconds() * 1000))
        sub_to_ack = max(0, int((ack_time - submission_time).total_seconds() * 1000))
        ack_to_fill = max(0, int((fill_time - ack_time).total_seconds() * 1000))
        total_delay = max(0, int((fill_time - signal_time).total_seconds() * 1000))
        
        return {
            "signal_to_submit_ms": sig_to_sub,
            "submit_to_ack_ms": sub_to_ack,
            "ack_to_fill_ms": ack_to_fill,
            "total_execution_delay_ms": total_delay,
        }
