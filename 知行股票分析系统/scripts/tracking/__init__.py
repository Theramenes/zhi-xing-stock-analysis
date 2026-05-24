"""追踪包 — 状态机 + 日终流程"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from state_machine import (
    transition, compute_next_stage, apply_transition, generate_alerts,
    WATCHING, NEAR_B1, B1, OBSERVING, BOUGHT, HOLDING, SELL_CANDIDATE, SOLD, ARCHIVED,
)
