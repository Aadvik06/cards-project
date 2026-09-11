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

    def test_travel_agent_card_payment_awards_base_points_only(self) -> None:
        recommendation = self.recommendations.create_recommendation(
            employee_id="emp-agent-card",
            travel_type=TravelType.HOTEL,
            quotes=[
                QuoteInput(
                    "travel_agent_hotel",
                    Decimal("10000"),
                    agent_payment_method="card",
                    agent_card_id="hdfc_infinia",
                )
            ],
        )
        selected = recommendation.ranked_options[0]

        self.assertEqual("hdfc_infinia", selected.card_id)
        self.assertEqual(Decimal("333.0000"), selected.base_points)
        self.assertEqual(Decimal("0.0000"), selected.awarded_bonus_points)
        self.assertEqual(selected.base_points, selected.total_points)

        transaction = self.transactions.finalize_transaction(
            recommendation_id=recommendation.id,
            selected_option_id=selected.id,
            final_amount_paid=Decimal("10000"),
            paid_at=datetime(2026, 8, 11, tzinfo=UTC),
        )

        self.assertEqual(Decimal("333.0000"), transaction.base_points)
        self.assertEqual(Decimal("0.0000"), transaction.bonus_points)
        self.assertEqual(transaction.base_points, transaction.total_points)

    def test_flight_gst_credit_reduces_ranked_net_cost_when_invoice_is_available(self) -> None:
        recommendation = self.recommendations.create_recommendation(
            employee_id="emp-gst-flight",
            travel_type=TravelType.FLIGHT,
            quotes=[
                QuoteInput(
                    "hdfc_smartbuy_flight",
                    Decimal("10500"),
                    gst_invoice_available=True,
                    origin_state="Maharashtra",
                    destination_state="Delhi",
                )
            ],
        )
        option = recommendation.ranked_options[0]

        self.assertTrue(option.gst_claimable)
        self.assertEqual(Decimal("500.00"), option.gst_credit)
        self.assertEqual(Decimal("5501.75"), option.net_cost)
        self.assertEqual(Decimal("2750.00"), option.tax_benefit)

    def test_hotel_gst_credit_only_applies_in_company_registered_states(self) -> None:
        allowed = self.recommendations.create_recommendation(
            employee_id="emp-gst-hotel",
            travel_type=TravelType.HOTEL,
            quotes=[
                QuoteInput(
                    "hdfc_smartbuy_hotel",
                    Decimal("11800"),
                    gst_invoice_available=True,
                    hotel_state="Maharashtra",
                )
            ],
        ).ranked_options[0]
        blocked = self.recommendations.create_recommendation(
            employee_id="emp-gst-hotel",
            travel_type=TravelType.HOTEL,
            quotes=[
                QuoteInput(
                    "hdfc_smartbuy_hotel",
                    Decimal("11800"),
                    gst_invoice_available=True,
                    hotel_state="Delhi",
                )
            ],
        ).ranked_options[0]

        self.assertTrue(allowed.gst_claimable)
        self.assertEqual(Decimal("1800.00"), allowed.gst_credit)
        self.assertFalse(blocked.gst_claimable)
        self.assertEqual(Decimal("0.00"), blocked.gst_credit)
        self.assertEqual(Decimal("3245.00"), blocked.tax_benefit)
        self.assertLess(allowed.net_cost, blocked.net_cost)

    def test_non_claimable_flight_gst_gets_tax_benefit_on_gst_component(self) -> None:
        recommendation = self.recommendations.create_recommendation(
            employee_id="emp-tax-benefit",
            travel_type=TravelType.FLIGHT,
            quotes=[
                QuoteInput(
                    "hdfc_smartbuy_flight",
                    Decimal("10500"),
                    gst_invoice_available=False,
                    origin_state="Maharashtra",
                    destination_state="Delhi",
                )
            ],
        )
        option = recommendation.ranked_options[0]

        self.assertFalse(option.gst_claimable)
        self.assertEqual(Decimal("0.00"), option.gst_credit)
        self.assertEqual(Decimal("2887.50"), option.tax_benefit)

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

    def test_transaction_details_can_be_directly_updated_without_changing_calculations(self) -> None:
        transaction = self.transactions.log_voucher_purchase(
            employee_name="Ava Patel",
            vendor_name="Office Supply Voucher",
            final_amount_paid=Decimal("1000"),
            paid_at=datetime(2026, 8, 11, tzinfo=UTC),
            description="Original note.",
        )

        self.assertTrue(self.ledger.update_transaction_details(
            transaction.id,
            {"vendor_name": "Client Gift Voucher", "description": "Corrected note."},
        ))

        updated = self.ledger.read_transactions()[0]
        self.assertEqual("Client Gift Voucher", updated["details"]["vendor_name"])
        self.assertEqual("Corrected note.", updated["details"]["description"])
        self.assertEqual(Decimal("1000.00"), Decimal(updated["final_amount_paid"]))
        self.assertEqual(Decimal("300.0000"), Decimal(updated["total_points"]))

    def test_database_keepalive_uses_a_lightweight_query(self) -> None:
        self.ledger.keepalive()

    def test_invoice_is_stored_with_pending_status_until_uploaded(self) -> None:
        transaction = self.transactions.log_voucher_purchase(
            employee_name="Ava Patel",
            vendor_name="Office Supply Voucher",
            final_amount_paid=Decimal("1000"),
            paid_at=datetime(2026, 8, 11, tzinfo=UTC),
            description="Invoice audit test.",
        )
        self.assertEqual("pending", self.ledger.read_transactions()[0]["invoice_status"])

        saved = self.ledger.save_invoice(
            transaction_id=transaction.id,
            filename="invoice.pdf",
            content_type="application/pdf",
            content=b"%PDF-test",
        )
        invoice = self.ledger.get_invoice(transaction.id)

        self.assertEqual("uploaded", saved["invoice_status"])
        self.assertTrue(invoice["filename"].endswith("_Office-Supply-Voucher_Invoice-T01.pdf"))
        self.assertEqual(b"%PDF-test", invoice["file_data"])
        self.assertEqual("uploaded", self.ledger.read_transactions()[0]["invoice_status"])
        invoice_list = self.ledger.read_invoices()
        self.assertEqual(1, len(invoice_list))
        self.assertEqual(transaction.id, invoice_list[0]["transaction_id"])
        self.assertEqual(invoice["filename"], invoice_list[0]["filename"])
        storage = self.ledger.invoice_storage_summary(1024)
        self.assertEqual(9, storage["used_bytes"])
        self.assertEqual(1, storage["invoice_count"])
        self.assertEqual(1015, storage["remaining_bytes"])
        self.assertTrue(self.ledger.delete_invoice(transaction.id))
        self.assertEqual("pending", self.ledger.read_transactions()[0]["invoice_status"])
        self.assertEqual(0, self.ledger.invoice_storage_summary(1024)["used_bytes"])

    def test_multiple_drafts_are_saved_in_database(self) -> None:
        drafts = [
            self.ledger.save_draft(
                draft_id=None,
                title=f"Flight draft {index}",
                travel_type="flight",
                current_step=2,
                data={"values": {"employeeName": "Ava", "draftNumber": index}},
                created_by="ava@example.com",
            )
            for index in range(1, 11)
        ]

        self.assertEqual(10, len({draft["id"] for draft in drafts}))
        self.assertEqual(10, len(self.ledger.read_drafts()))
        self.assertEqual("Flight draft 1", self.ledger.get_draft(drafts[0]["id"])["title"])
        self.assertTrue(self.ledger.delete_draft(drafts[-1]["id"]))
        self.assertEqual(9, len(self.ledger.read_drafts()))

    def test_amex_travel_voucher_discount_uses_purchase_cost_and_card_balance(self) -> None:
        recommendation = self.recommendations.create_recommendation(
            employee_id="emp-amex",
            travel_type=TravelType.FLIGHT,
            quotes=[
                QuoteInput(
                    "amex_mmt_flight_voucher",
                    Decimal("10200"),
                    discount_rate=Decimal("0.02"),
                    voucher_face_value=Decimal("10000"),
                    gst_invoice_available=True,
                    origin_state="Maharashtra",
                    destination_state="Delhi",
                )
            ],
        )
        selected = recommendation.ranked_options[0]

        self.assertEqual(Decimal("10000.00"), selected.eligible_amount)
        self.assertEqual(Decimal("200.00"), selected.cash_component)
        self.assertEqual(Decimal("10000.00"), selected.price_after_discount)
        self.assertEqual(Decimal("300.0000"), selected.base_points)
        self.assertEqual(Decimal("2646.0000"), selected.awarded_bonus_points)
        self.assertEqual(Decimal("2946.0000"), selected.total_points)
        self.assertEqual(Decimal("485.71"), selected.gst_credit)

        transaction = self.transactions.finalize_transaction(
            recommendation_id=recommendation.id,
            selected_option_id=selected.id,
            final_amount_paid=Decimal("10000"),
            paid_at=datetime(2026, 8, 11, tzinfo=UTC),
            details={
                "description": "Amex discounted voucher plus card balance.",
                "voucher_face_value_used": "10000",
                "voucher_purchase_amount_paid": "9800",
                "card_balance_paid": "200",
            },
        )

        self.assertEqual(Decimal("10000.00"), transaction.final_amount_paid)
        self.assertEqual(Decimal("300.0000"), transaction.base_points)
        self.assertEqual(Decimal("2646.0000"), transaction.bonus_points)
        self.assertEqual(Decimal("2946.0000"), transaction.total_points)
        self.assertEqual(Decimal("4869.04"), transaction.net_cost)

    def test_amex_travel_voucher_split_awards_bonus_only_on_voucher_purchase_cost(self) -> None:
        recommendation = self.recommendations.create_recommendation(
            employee_id="emp-amex",
            travel_type=TravelType.FLIGHT,
            quotes=[QuoteInput("amex_mmt_flight_voucher", Decimal("12000"))],
        )
        selected = recommendation.ranked_options[0]

        transaction = self.transactions.finalize_transaction(
            recommendation_id=recommendation.id,
            selected_option_id=selected.id,
            final_amount_paid=Decimal("12000"),
            paid_at=datetime(2026, 8, 11, tzinfo=UTC),
            details={
                "description": "Amex voucher split.",
                "voucher_face_value_used": "10000",
                "voucher_purchase_amount_paid": "10000",
                "card_balance_paid": "2000",
            },
        )

        self.assertEqual(Decimal("360.0000"), transaction.base_points)
        self.assertEqual(Decimal("2700.0000"), transaction.bonus_points)
        self.assertEqual(Decimal("3060.0000"), transaction.total_points)

    def test_amex_travel_voucher_allows_zero_voucher_value(self) -> None:
        recommendation = self.recommendations.create_recommendation(
            employee_id="emp-no-voucher-used",
            travel_type=TravelType.FLIGHT,
            quotes=[
                QuoteInput(
                    "amex_mmt_flight_voucher",
                    Decimal("12000"),
                    voucher_face_value=Decimal("0"),
                )
            ],
        )
        selected = recommendation.ranked_options[0]

        self.assertEqual(Decimal("0.00"), selected.eligible_amount)
        self.assertEqual(Decimal("12000.00"), selected.cash_component)
        self.assertEqual(Decimal("0.0000"), selected.awarded_bonus_points)

        transaction = self.transactions.finalize_transaction(
            recommendation_id=recommendation.id,
            selected_option_id=selected.id,
            final_amount_paid=Decimal("12000"),
            paid_at=datetime(2026, 8, 11, tzinfo=UTC),
            details={
                "description": "Voucher option selected without using a voucher.",
                "voucher_face_value_used": "0",
                "voucher_purchase_amount_paid": "0",
                "card_balance_paid": "12000",
            },
        )

        self.assertEqual(Decimal("0.0000"), transaction.bonus_points)
        self.assertEqual(Decimal("360.0000"), transaction.total_points)

    def test_points_redeemed_reduce_rewardable_spend_for_hdfc(self) -> None:
        recommendation = self.recommendations.create_recommendation(
            employee_id="emp-redemption",
            travel_type=TravelType.FLIGHT,
            quotes=[QuoteInput("hdfc_smartbuy_flight", Decimal("10000"))],
        )
        selected = recommendation.ranked_options[0]

        transaction = self.transactions.finalize_transaction(
            recommendation_id=recommendation.id,
            selected_option_id=selected.id,
            final_amount_paid=Decimal("10000"),
            points_used=Decimal("1000"),
            paid_at=datetime(2026, 8, 11, tzinfo=UTC),
            details={"description": "HDFC points redemption."},
        )

        self.assertEqual(Decimal("1000.0000"), transaction.points_used)
        self.assertEqual(Decimal("299.7000"), transaction.base_points)
        self.assertEqual(Decimal("1498.5000"), transaction.total_points)

    def test_international_flight_estimates_gst_by_india_originating_sector_share(self) -> None:
        def option_for(*, sector_count: int, flight_class: str = "Economy"):
            return self.recommendations.create_recommendation(
                employee_id=f"emp-international-{sector_count}-{flight_class}",
                travel_type=TravelType.FLIGHT,
                quotes=[
                    QuoteInput(
                        "hdfc_smartbuy_flight",
                        Decimal("10500" if flight_class == "Economy" else "11800"),
                        gst_invoice_available=True,
                        origin_state="Maharashtra",
                        destination_state="Outside India",
                        flight_class=flight_class,
                        flight_sector_count=sector_count,
                    )
                ],
            ).ranked_options[0]

        mumbai_to_dubai = option_for(sector_count=1)
        mumbai_to_london_via_dubai = option_for(sector_count=2)
        return_with_connections = option_for(sector_count=4)
        premium_return = option_for(sector_count=2, flight_class="Business")

        self.assertTrue(mumbai_to_dubai.foreign_transaction)
        self.assertEqual(Decimal("500.00"), mumbai_to_dubai.gst_credit)
        self.assertEqual(Decimal("250.00"), mumbai_to_london_via_dubai.gst_credit)
        self.assertEqual(Decimal("125.00"), return_with_connections.gst_credit)
        self.assertEqual(Decimal("0.18"), premium_return.gst_rate)
        self.assertEqual(Decimal("900.00"), premium_return.gst_credit)
        self.assertIn("50.0%", mumbai_to_london_via_dubai.gst_note)


if __name__ == "__main__":
    unittest.main()
