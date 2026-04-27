"""
Seed script — populates the database with initial test data.

Usage:
    python -m app.seed

This script is idempotent-ish: it only creates data if the tables are empty,
so running it twice won't duplicate everything.
"""
from app.database import init_db, get_db
from app.models import User, Task, GroceryItem


def seed():
    init_db()

    with get_db() as db:
        # --- Users ---
        if db.query(User).count() == 0:
            print("→ Creating users...")
            alice = User(name="Alice", avatar_color="purple")
            alice.set_password("alice123")  # change in production!

            bob = User(name="Bob", avatar_color="teal")
            bob.set_password("bob123")

            db.add_all([alice, bob])
            db.flush()
            print(f"  ✓ {alice.name} (password: alice123)")
            print(f"  ✓ {bob.name} (password: bob123)")
        else:
            print("→ Users already exist, skipping.")

        # --- Sample Tasks ---
        if db.query(Task).count() == 0:
            print("→ Creating sample tasks...")
            tasks = [
                Task(
                    name="Make the bed",
                    description="Tidy up the bedroom every morning",
                    frequency_type="daily",
                    frequency_config={},
                ),
                Task(
                    name="Take out the trash",
                    description="Tuesday and Friday are pickup days",
                    frequency_type="specific_days",
                    frequency_config={"weekdays": [1, 4]},  # Tue, Fri
                ),
                Task(
                    name="Water the plants",
                    description="Living room and balcony plants",
                    frequency_type="weekly",
                    frequency_config={"weekday": 6},  # Sunday
                ),
                Task(
                    name="Wash the car",
                    description="Quick rinse if not raining",
                    frequency_type="daily",
                    frequency_config={},
                ),
            ]
            db.add_all(tasks)
            for t in tasks:
                print(f"  ✓ {t.name} ({t.frequency_type})")
        else:
            print("→ Tasks already exist, skipping.")

        # --- Sample Grocery Items (with varied counts to test sort) ---
        if db.query(GroceryItem).count() == 0:
            print("→ Creating sample grocery items...")
            items = [
                GroceryItem(name="Café", category="Despensa", purchase_count=15),
                GroceryItem(name="Arroz", category="Despensa", purchase_count=14),
                GroceryItem(name="Frijoles", category="Despensa", purchase_count=13),
                GroceryItem(name="Aceite", category="Despensa", purchase_count=11),
                GroceryItem(name="Leche", category="Carnes y Lácteos", purchase_count=12),
                GroceryItem(name="Huevos", category="Carnes y Lácteos", purchase_count=10),
                GroceryItem(name="Queso", category="Carnes y Lácteos", purchase_count=7),
                GroceryItem(name="Pollo", category="Carnes y Lácteos", purchase_count=6),
                GroceryItem(name="Tomates", category="Frescos", purchase_count=9),
                GroceryItem(name="Cebollas", category="Frescos", purchase_count=8),
                GroceryItem(name="Aguacates", category="Frescos", purchase_count=5),
                GroceryItem(name="Loroco", category="Frescos", purchase_count=4),
                GroceryItem(name="Tortillas", category="Panadería", purchase_count=10),
                GroceryItem(name="Pan francés", category="Panadería", purchase_count=8),
                GroceryItem(name="Papel higiénico", category="Cuidado Personal", purchase_count=9),
                GroceryItem(name="Shampoo", category="Cuidado Personal", purchase_count=5),
                GroceryItem(name="Jabón de platos", category="Limpieza del Hogar", purchase_count=6),
                GroceryItem(name="Detergente", category="Limpieza del Hogar", purchase_count=5),
                GroceryItem(name="Comida para gato", category="Mascotas", purchase_count=8),
            ]
            db.add_all(items)
            for i in items:
                print(f"  ✓ {i.name} ({i.category}, bought {i.purchase_count}x)")
        else:
            print("→ Grocery items already exist, skipping.")

    print("\n✅ Seed complete!")


if __name__ == "__main__":
    seed()