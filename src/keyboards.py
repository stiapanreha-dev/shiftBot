"""Inline keyboards for Telegram bot."""

from typing import List, Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from config import Config
from src.time_utils import generate_am_times, generate_pm_times


def date_choice_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard for choosing shift start date.

    Returns:
        InlineKeyboardMarkup with date options.
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Yesterday", callback_data="DATE_IN:-1")],
        [InlineKeyboardButton("Today", callback_data="DATE_IN:0")],
        [InlineKeyboardButton("⬅️ Back", callback_data="BACK")],
    ])


def date_choice_edit_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard for choosing date when editing Clock in.

    Returns:
        InlineKeyboardMarkup with date options relative to record date.
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("The day BEFORE the record", callback_data="EDIT_DATE_IN:-1")],
        [InlineKeyboardButton("The SAME day as the record", callback_data="EDIT_DATE_IN:0")],
        [InlineKeyboardButton("⬅️ Back", callback_data="BACK")],
    ])


def time_keyboard(kind: str, daypart: str, mode: str = "normal") -> InlineKeyboardMarkup:
    """Create keyboard for time selection.

    Args:
        kind: 'IN' or 'OUT' for Clock in/out.
        daypart: 'AM' or 'PM'.
        mode: 'normal' for shift creation or 'edit' for editing.

    Returns:
        InlineKeyboardMarkup with time buttons.
    """
    times = generate_am_times() if daypart == "AM" else generate_pm_times()
    buttons = []

    # Choose prefix based on mode
    time_prefix = "EDIT_TIME" if mode == "edit" else "TIME"
    switch_prefix = "EDIT_SWITCH" if mode == "edit" else "SWITCH"

    # Create 3 rows × 4 buttons
    for row in range(3):
        row_buttons = []
        for col in range(4):
            idx = row * 4 + col
            label = times[idx]
            callback_data = f"{time_prefix}:{kind}:{label.replace(' ', '_')}"
            row_buttons.append(InlineKeyboardButton(label, callback_data=callback_data))
        buttons.append(row_buttons)

    # Add switch button (13th button)
    other_daypart = "PM" if daypart == "AM" else "AM"
    buttons.append([
        InlineKeyboardButton(
            f"→ {other_daypart}",
            callback_data=f"{switch_prefix}:{kind}:{other_daypart}"
        )
    ])

    # Add Back button
    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="BACK")])

    return InlineKeyboardMarkup(buttons)


def products_keyboard(exclude: Optional[List[str]] = None) -> InlineKeyboardMarkup:
    """Create keyboard for product selection.

    Args:
        exclude: List of products to exclude (already added).

    Returns:
        InlineKeyboardMarkup with product buttons.
    """
    exclude = exclude or []
    available_products = [p for p in Config.PRODUCTS if p not in exclude]

    buttons = []
    row = []

    for i, product in enumerate(available_products, start=1):
        row.append(InlineKeyboardButton(product, callback_data=f"PROD:{product}"))

        # 3 products per row
        if i % 3 == 0:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="BACK")])

    return InlineKeyboardMarkup(buttons)


def add_or_finish_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard for Add model / Finish shift choice.

    Returns:
        InlineKeyboardMarkup with options.
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Add model", callback_data="ADD_MODEL")],
        [InlineKeyboardButton("Finish shift", callback_data="FINISH")],
        [InlineKeyboardButton("⬅️ Back", callback_data="BACK")],
    ])


def start_menu_keyboard() -> InlineKeyboardMarkup:
    """Create start menu keyboard with all options.

    Returns:
        InlineKeyboardMarkup with start options.
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Create new shift", callback_data="CREATE_SHIFT")],
        [InlineKeyboardButton("Edit shift", callback_data="EDIT_SHIFT")],
        [InlineKeyboardButton("📊 Statistics", callback_data="STATISTICS")],
        [InlineKeyboardButton("🏆 Ranks", callback_data="RANKS")],
    ])


def edit_fields_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard for selecting field to edit.

    Returns:
        InlineKeyboardMarkup with editable fields.
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Clock in", callback_data="EDIT_FIELD:IN")],
        [InlineKeyboardButton("Clock out", callback_data="EDIT_FIELD:OUT")],
        [InlineKeyboardButton("Total sales", callback_data="EDIT_FIELD:TOTAL")],
        [InlineKeyboardButton("⬅️ Back", callback_data="BACK")],
    ])


def main_menu_button() -> InlineKeyboardMarkup:
    """Create keyboard with 'Main menu' button.

    Returns:
        InlineKeyboardMarkup with Main menu button.
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Main menu", callback_data="MAIN_MENU")],
    ])


def claim_rank_button() -> InlineKeyboardMarkup:
    """Create keyboard with 'Claim' button for rank notifications.

    Returns:
        InlineKeyboardMarkup with Claim button.
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Claim", callback_data="MAIN_MENU")],
    ])


def shifts_list_keyboard(shifts: List[dict]) -> InlineKeyboardMarkup:
    """Create keyboard with list of shifts to edit.

    Args:
        shifts: List of shift dictionaries.

    Returns:
        InlineKeyboardMarkup with shift buttons.
    """
    buttons = []

    for shift in shifts:
        shift_id = shift.get("ID", "?")
        date = shift.get("Date", "?")
        label = f"ID {shift_id} • {date}"
        buttons.append([
            InlineKeyboardButton(label, callback_data=f"EDIT_PICK:{shift_id}")
        ])

    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="BACK")])

    return InlineKeyboardMarkup(buttons)
