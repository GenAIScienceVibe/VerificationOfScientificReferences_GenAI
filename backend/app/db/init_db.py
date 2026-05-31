from .database import init_db
from .seed import seed_demo_data


def main() -> None:
    init_db()
    seed_demo_data()
    print("Database schema created and demo data seeded.")


if __name__ == "__main__":
    main()
