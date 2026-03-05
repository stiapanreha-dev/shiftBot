"""Main handlers re-export facade.

All handler implementations have been moved to submodules under src/handlers/.
This file re-exports them for backward compatibility.
"""

from src.handlers.shift_create import (
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

from src.handlers.shift_edit import (
    start_edit_shift,
    handle_edit_pick_shift,
    handle_edit_field_choice,
    handle_edit_date_choice,
    handle_edit_time_in,
    handle_edit_time_out,
    handle_edit_total_sales_input,
)

from src.handlers.stats import (
    show_statistics,
    show_ranks_info,
    show_hush_balance,
)

from src.handlers.callback_router import (
    handle_callback_query,
    handle_unexpected_text,
)

from src.handlers.admin import (
    recalc_ranks_command,
    withdraw_hush_command,
    ADMIN_IDS,
)
