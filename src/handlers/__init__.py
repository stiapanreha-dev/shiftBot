"""Handlers package for Telegram bot.

This package contains modular handlers split by functionality:
- navigation: State management and keyboard utilities
- utils: Parsing, formatting, and message building
- shift_create: Shift creation flow handlers
- shift_edit: Shift editing flow handlers
- stats: Statistics, ranks info, and HUSH balance handlers
- callback_router: Callback query routing and unexpected text handler
- admin: Admin command handlers
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

# Shift creation handlers
from .shift_create import (
    start,
    start_create_shift,
    handle_date_choice,
    handle_time_switch,
    handle_time_choice_in,
    handle_time_choice_out,
    handle_product_choice,
    handle_amount_input,
    handle_add_model,
    handle_finish_shift,
    check_and_notify_rank,
)

# Shift editing handlers
from .shift_edit import (
    start_edit_shift,
    handle_edit_pick_shift,
    handle_edit_field_choice,
    handle_edit_date_choice,
    handle_edit_time_in,
    handle_edit_time_out,
    handle_edit_total_sales_input,
)

# Statistics handlers
from .stats import (
    show_statistics,
    show_ranks_info,
    show_hush_balance,
)

# Callback routing
from .callback_router import (
    handle_callback_query,
    handle_unexpected_text,
)

# Admin commands
from .admin import (
    recalc_ranks_command,
    withdraw_hush_command,
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
    # Shift creation
    'start',
    'start_create_shift',
    'handle_date_choice',
    'handle_time_switch',
    'handle_time_choice_in',
    'handle_time_choice_out',
    'handle_product_choice',
    'handle_amount_input',
    'handle_add_model',
    'handle_finish_shift',
    'check_and_notify_rank',
    # Shift editing
    'start_edit_shift',
    'handle_edit_pick_shift',
    'handle_edit_field_choice',
    'handle_edit_date_choice',
    'handle_edit_time_in',
    'handle_edit_time_out',
    'handle_edit_total_sales_input',
    # Stats
    'show_statistics',
    'show_ranks_info',
    'show_hush_balance',
    # Callback routing
    'handle_callback_query',
    'handle_unexpected_text',
    # Admin
    'recalc_ranks_command',
    'withdraw_hush_command',
    'ADMIN_IDS',
]
