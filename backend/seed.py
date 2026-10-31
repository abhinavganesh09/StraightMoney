"""Seed the section 14 demo campaign, vendors, and budget lines."""

from __future__ import annotations

from sqlalchemy.orm import Session

from models import BudgetLine, Campaign, Vendor


def seed_demo_data(db: Session) -> None:
    """Insert the demo campaign once; leave donations to the PayPal flow."""
    if db.query(Campaign).filter_by(title="School Library Corner").first():
        return

    campaign = Campaign(
        title="School Library Corner",
        description="A school library corner with shelves, books, and paint.",
        goal_amount=1200.0,
        currency="USD",
        pool_balance=0.0,
        status="active",
        organizer_name="Demo Organizer",
    )
    db.add(campaign)
    db.flush()

    for name, email, item, amount in (
        ("Vendor A", "vendor-a@example.com", "Shelves", 400.0),
        ("Vendor B", "vendor-b@example.com", "Books", 600.0),
        ("Vendor C", "vendor-c@example.com", "Paint", 200.0),
    ):
        vendor = Vendor(
            campaign_id=campaign.id,
            name=name,
            payout_email=email,
            status="active",
        )
        db.add(vendor)
        db.flush()
        db.add(BudgetLine(
            campaign_id=campaign.id,
            name=item,
            vendor_id=vendor.id,
            budgeted_amount=amount,
            paid_amount=0.0,
        ))
    db.commit()


if __name__ == "__main__":
    from db import SessionLocal, init_db

    init_db()
    with SessionLocal() as session:
        seed_demo_data(session)
        campaign = session.query(Campaign).filter_by(title="School Library Corner").one()
        print(f"Seed ready: campaign={campaign.title}, vendors={len(campaign.vendors)}, budget_lines={len(campaign.budget_lines)}")
