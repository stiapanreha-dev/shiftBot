"""Handlers package for Telegram bot.

This package contains modular handlers split by functionality:
- navigation: State management and keyboard utilities
- utils: Parsing, formatting, and message building
- (more modules to be added as refactoring continues)

For backward compatibility, all handlers are re-exported from this module.
"""

# Navigation utilities
from .navigation import (
    push_state,
    go_back,
    reset_flow,
    remove_keyboard,
    remove_last_keyboard,
    send_keyboard_message,
)

# Utility functions
from .utils import (
    parse_amount,
    get_commission_breakdown,
    format_shift_totals,
    format_shift_details,
    build_summary,
)

# Re-export everything from the main handlers module for backward compatibility
# This allows existing code to continue using:
#   from src.handlers import start, handle_callback_query, etc.

# Import the main handlers module to get remaining handlers
# These will be moved to separate modules in future refactoring
from src.handlers_main import (
    start,
    handle_callback_query,
    handle_amount_input,
    handle_edit_total_sales_input,
    handle_unexpected_text,
    recalc_ranks_command,
    withdraw_hush_command,
    # Additional handlers for bot.py
    start_create_shift,
    handle_date_choice,
    handle_time_switch,
    handle_time_choice_in,
    handle_time_choice_out,
    handle_product_choice,
    handle_add_model,
    handle_finish_shift,
    start_edit_shift,
    handle_edit_pick_shift,
    handle_edit_field_choice,
    handle_edit_date_choice,
    handle_edit_time_in,
    handle_edit_time_out,
    show_statistics,
    show_ranks_info,
    show_hush_balance,
    check_and_notify_rank,
    ADMIN_IDS,
)

__all__ = [
    # Navigation
    'push_state',
    'go_back',
    'reset_flow',
    'remove_keyboard',
    'remove_last_keyboard',
    'send_keyboard_message',
    # Utils
    'parse_amount',
    'get_commission_breakdown',
    'format_shift_totals',
    'format_shift_details',
    'build_summary',
    # Main handlers
    'start',
    'handle_callback_query',
    'handle_amount_input',
    'handle_edit_total_sales_input',
    'handle_unexpected_text',
    'recalc_ranks_command',
    'withdraw_hush_command',
    'start_create_shift',
    'handle_date_choice',
    'handle_time_switch',
    'handle_time_choice_in',
    'handle_time_choice_out',
    'handle_product_choice',
    'handle_add_model',
    'handle_finish_shift',
    'start_edit_shift',
    'handle_edit_pick_shift',
    'handle_edit_field_choice',
    'handle_edit_date_choice',
    'handle_edit_time_in',
    'handle_edit_time_out',
    'show_statistics',
    'show_ranks_info',
    'show_hush_balance',
    'check_and_notify_rank',
    'ADMIN_IDS',
]
