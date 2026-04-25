"""
Grocery service — Module 2 logic.

Key responsibilities:
  - Fetching the current pending shopping list.
  - Producing the dropdown suggestions sorted by purchase frequency.
  - Adding items to the active list (creating new GroceryItem rows when needed).
  - Marking items as purchased (which increments the popularity counter).
"""
from datetime import datetime
from sqlalchemy import or_, func
from sqlalchemy.orm import Session

from app.models import GroceryItem, ActiveShoppingItem


def get_active_list(db: Session) -> list[ActiveShoppingItem]:
    """Items currently on the shopping list (not yet bought)."""
    return (
        db.query(ActiveShoppingItem)
        .filter(ActiveShoppingItem.is_purchased.is_(False))
        .order_by(ActiveShoppingItem.added_at.desc())
        .all()
    )


def search_suggestions(db: Session, query: str = "", limit: int = 20) -> list[GroceryItem]:
    """
    Suggestions for the smart-add combo box.

    Sort logic:
      1. Most-purchased first  (purchase_count DESC)
      2. Recently bought as tiebreaker  (last_purchased_at DESC)

    If the user typed something, filter by name LIKE '%query%'.
    """
    q = db.query(GroceryItem)

    if query.strip():
        # Case-insensitive match — SQLite's LIKE is case-insensitive for ASCII.
        like = f"%{query.strip()}%"
        q = q.filter(GroceryItem.name.ilike(like))

    return (
        q.order_by(
            GroceryItem.purchase_count.desc(),
            GroceryItem.last_purchased_at.desc().nullslast(),
            GroceryItem.name.asc(),
        )
        .limit(limit)
        .all()
    )


def add_to_active_list(
    db: Session,
    item_name: str,
    user_id: int,
    category: str = "Food",
) -> ActiveShoppingItem:
    """
    Add an item to the shopping list.

    Behavior:
      - If the item exists in the library AND is not already pending, add it.
      - If it exists AND is already pending, do nothing (no duplicates).
      - If it doesn't exist, create a new GroceryItem first, then add it.
    """
    name_clean = item_name.strip()
    if not name_clean:
        raise ValueError("Item name cannot be empty")

    # Look up or create the library item (case-insensitive match)
    item = (
        db.query(GroceryItem)
        .filter(func.lower(GroceryItem.name) == name_clean.lower())
        .first()
    )
    if item is None:
        item = GroceryItem(name=name_clean, category=category, purchase_count=0)
        db.add(item)
        db.flush()

    # Check for an existing pending entry (avoid duplicates)
    existing = (
        db.query(ActiveShoppingItem)
        .filter(
            ActiveShoppingItem.item_id == item.id,
            ActiveShoppingItem.is_purchased.is_(False),
        )
        .first()
    )
    if existing:
        return existing

    entry = ActiveShoppingItem(
        item_id=item.id,
        added_by_user_id=user_id,
        is_purchased=False,
    )
    db.add(entry)
    db.flush()
    return entry


def mark_as_purchased(db: Session, active_item_id: int) -> None:
    """
    Mark an item as bought.

    Side effects:
      - Sets is_purchased=True and stamps purchased_at.
      - Increments purchase_count on the parent GroceryItem
        (this is what powers the "most bought first" sorting).
    """
    entry = (
        db.query(ActiveShoppingItem)
        .filter(ActiveShoppingItem.id == active_item_id)
        .first()
    )
    if not entry:
        return

    now = datetime.utcnow()
    entry.is_purchased = True
    entry.purchased_at = now
    entry.item.purchase_count += 1
    entry.item.last_purchased_at = now


def remove_from_active_list(db: Session, active_item_id: int) -> None:
    """
    Remove an item from the active list WITHOUT marking it purchased.

    Use case: user added something by mistake.
    Important: this does NOT increment purchase_count.
    """
    entry = (
        db.query(ActiveShoppingItem)
        .filter(ActiveShoppingItem.id == active_item_id)
        .first()
    )
    if entry:
        db.delete(entry)