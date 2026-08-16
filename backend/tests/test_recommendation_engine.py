import tempfile
import unittest
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from app.core.errors import InvalidDecisionError
from app.data.repositories.audit_ledger import AuditLedger
from app.domain.enums import TravelType
from app.domain.models import QuoteInput
from app.services.recommendation_service import RecommendationService
from app.services.transaction_service import TransactionService


class RecommendationEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.ledger = AuditLedger(Path(self.tmpdir.name))
        self.recommendations = RecommendationService(ledger=self.ledger)
        self.transactions = TransactionService(self.recommendations)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_flight_examples_are_ranked_best_to_worst(self) -> None:
        recommendation = self.recommendations.create_recommendation(
            employee_id="emp-1",
            travel_type=TravelType.FLIGHT,
            travel_date=datetime(2026, 8, 11, tzinfo=UTC).date(),
            quotes=[
                QuoteInput("amex_mmt_flight_voucher", Decimal("11480")),
                QuoteInput("amex_cleartrip_generic_voucher", Decimal("12055"), discount_rate=Decimal("0.023")),
                QuoteInput("hdfc_smartbuy_flight", Decimal("10869")),
                QuoteInput("icici_ishop_flight", Decimal("11016")),
            ],
        )

        self.assertEqual("hdfc_infinia", recommendation.ranked_options[0].card_id)
        self.assertEqual("hdfc_smartbuy_flight", recommendation.ranked_options[0].vendor_id)
        self.assertEqual(Decimal("9059.31"), recommendation.ranked_options[0].net_cost)
        self.assertEqual(
            ["hdfc_infinia", "amex", "icici_times_black"],
            [option.card_id for option in recommendation.card_rankings],
        )

    def test_hotel_examples_are_ranked_best_to_worst(self) -> None:
        recommendation = self.recommendations.create_recommendation(
            employee_id="emp-2",
            travel_type=TravelType.HOTEL,
            travel_date=datetime(2026, 8, 11, tzinfo=UTC).date(),
            quotes=[
                QuoteInput("amex_goibibo_hotel_voucher", Decimal("11480"), discount_rate=Decimal("0.021")),
                QuoteInput("amex_easemytrip_hotel_voucher", Decimal("12744"), discount_rate=Decimal("0.021")),
                QuoteInput("amex_mmt_hotel_voucher", Decimal("13020"), discount_rate=Decimal("0.066")),
                QuoteInput("amex_cleartrip_hotel_voucher", Decimal("11800"), discount_rate=Decimal("0.023")),
                QuoteInput("hdfc_smartbuy_hotel", Decimal("12801")),
                QuoteInput("icici_ishop_hotel", Decimal("12683")),
                QuoteInput("amex_fine_hotels", Decimal("10000")),
            ],
        )

        self.assertEqual("hdfc_infinia", recommendation.ranked_options[0].card_id)
        self.assertEqual("hdfc_smartbuy_hotel", recommendation.ranked_options[0].vendor_id)
        self.assertEqual(Decimal("8538.27"), recommendation.ranked_options[0].net_cost)
        self.assertEqual(3, len(recommendation.card_rankings))

    def test_decline_requires_reason_and_does_not_write_transaction_log(self) -> None:
        recommendation = self.recommendations.create_recommendation(
            employee_id="emp-3",
            travel_type=TravelType.FLIGHT,
            quotes=[QuoteInput("hdfc_smartbuy_flight", Decimal("10869"))],
        )

        with self.assertRaises(InvalidDecisionError):
            self.recommendations.record_decision(
                recommendation_id=recommendation.id,
                accepted=False,
            )

        self.recommendations.record_decision(
            recommendation_id=recommendation.id,
            accepted=False,
            decline_reason="Employee needed a card with a higher reimbursement limit.",
        )
        self.assertEqual(1, len(self.ledger.read_decisions()))
        self.assertEqual(0, len(self.ledger.read_transactions()))

    def test_transaction_is_logged_only_after_final_amount_is_submitted(self) -> None:
        recommendation = self.recommendations.create_recommendation(
            employee_id="emp-4",
            travel_type=TravelType.FLIGHT,
            quotes=[
                QuoteInput("hdfc_smartbuy_flight", Decimal("10869")),
                QuoteInput("amex_mmt_flight_voucher", Decimal("11480")),
            ],
        )
        selected = recommendation.ranked_options[0]

        self.assertEqual(0, len(self.ledger.read_transactions()))

        self.recommendations.record_decision(
            recommendation_id=recommendation.id,
            accepted=True,
            selected_option_id=selected.id,
        )
        self.assertEqual(1, len(self.ledger.read_decisions()))
        self.assertEqual(0, len(self.ledger.read_transactions()))

        transaction = self.transactions.finalize_transaction(
            recommendation_id=recommendation.id,
            selected_option_id=selected.id,
            final_amount_paid=Decimal("10999"),
            paid_at=datetime(2026, 8, 11, tzinfo=UTC),
            details={"description": "Final checkout amount changed slightly."},
        )

        self.assertEqual(Decimal("10999.00"), transaction.final_amount_paid)
        self.assertEqual(1, len(self.ledger.read_transactions()))

    def test_travel_agent_option_is_comparison_only_bank_transfer(self) -> None:
        recommendation = self.recommendations.create_recommendation(
            employee_id="emp-agent",
            travel_type=TravelType.FLIGHT,
            quotes=[
                QuoteInput("hdfc_smartbuy_flight", Decimal("10869")),
                QuoteInput("travel_agent_flight", Decimal("9000")),
            ],
        )
        selected = recommendation.ranked_options[0]

        self.assertEqual("bank_transfer", selected.card_id)
        self.assertEqual("travel_agent_flight", selected.vendor_id)
        self.assertEqual(Decimal("9000.00"), selected.net_cost)
        self.assertEqual(Decimal("0.0000"), selected.total_points)

        transaction = self.transactions.finalize_transaction(
            recommendation_id=recommendation.id,
            selected_option_id=selected.id,
            final_amount_paid=Decimal("9100"),
            paid_at=datetime(2026, 8, 11, tzinfo=UTC),
            details={"description": "Travel agent bank transfer."},
        )

        self.assertEqual("bank_transfer", transaction.card_id)
        self.assertEqual(Decimal("9100.00"), transaction.final_amount_paid)
        self.assertEqual(Decimal("0.0000"), transaction.total_points)
        self.assertEqual(Decimal("9100.00"), transaction.net_cost)

    def test_finalized_history_reduces_future_available_caps(self) -> None:
        first = self.recommendations.create_recommendation(
            employee_id="emp-5",
            travel_type=TravelType.HOTEL,
            travel_date=datetime(2026, 8, 11, tzinfo=UTC).date(),
            quotes=[QuoteInput("hdfc_smartbuy_hotel", Decimal("100000"))],
        )
        first_option = first.ranked_options[0]
        self.transactions.finalize_transaction(
            recommendation_id=first.id,
            selected_option_id=first_option.id,
            final_amount_paid=Decimal("100000"),
            paid_at=datetime(2026, 8, 11, tzinfo=UTC),
            details={"description": "Large hotel booking to consume monthly cap."},
        )

        second = self.recommendations.create_recommendation(
            employee_id="emp-5",
            travel_type=TravelType.HOTEL,
            travel_date=datetime(2026, 8, 11, tzinfo=UTC).date(),
            quotes=[QuoteInput("hdfc_smartbuy_hotel", Decimal("10000"))],
        )

        self.assertEqual(Decimal("0.0000"), second.ranked_options[0].awarded_bonus_points)

    def test_recommendation_and_decision_survive_service_restart(self) -> None:
        db_path = Path(self.tmpdir.name) / "restart.sqlite3"
        first_service = RecommendationService(ledger=AuditLedger(db_path))
        recommendation = first_service.create_recommendation(
            employee_id="emp-6",
            travel_type=TravelType.FLIGHT,
            quotes=[QuoteInput("hdfc_smartbuy_flight", Decimal("10869"))],
        )
        first_service.record_decision(
            recommendation_id=recommendation.id,
            accepted=True,
            selected_option_id=recommendation.ranked_options[0].id,
        )

        restarted_service = RecommendationService(ledger=AuditLedger(db_path))
        restarted_transactions = TransactionService(restarted_service)

        transaction = restarted_transactions.finalize_transaction(
            recommendation_id=recommendation.id,
            final_amount_paid=Decimal("10899"),
            paid_at=datetime(2026, 8, 11, tzinfo=UTC),
            details={"description": "Finalize after service restart."},
        )

        self.assertEqual(recommendation.id, transaction.recommendation_id)
        self.assertEqual(1, len(restarted_service.ledger.read_transactions()))

    def test_voucher_purchase_logs_amex_points_without_recommendation(self) -> None:
        transaction = self.transactions.log_voucher_purchase(
            employee_name="Ava Patel",
            vendor_name="Office Supply Voucher",
            final_amount_paid=Decimal("10000"),
            paid_at=datetime(2026, 8, 11, tzinfo=UTC),
            description="Occasional non-travel voucher purchase.",
        )

        self.assertEqual("voucher", transaction.travel_type)
        self.assertEqual("amex", transaction.card_id)
        self.assertEqual(Decimal("3000.0000"), transaction.total_points)
        self.assertEqual(1, len(self.ledger.read_transactions()))

    def test_transaction_can_be_deleted(self) -> None:
        transaction = self.transactions.log_voucher_purchase(
            employee_name="Ava Patel",
            vendor_name="Office Supply Voucher",
            final_amount_paid=Decimal("1000"),
            paid_at=datetime(2026, 8, 11, tzinfo=UTC),
            description="Delete test voucher.",
        )

        self.assertTrue(self.ledger.delete_transaction(transaction.id))
        self.assertEqual(0, len(self.ledger.read_transactions()))


if __name__ == "__main__":
    unittest.main()
