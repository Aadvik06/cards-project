import calendar
import html
import os
import tempfile
from collections import defaultdict
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Iterable

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.services.monthly_log_service import MonthlyLogService


class ReportService:
    def __init__(
        self,
        monthly_log_service: MonthlyLogService,
        output_dir: Path | str | None = None,
    ) -> None:
        self.monthly_log_service = monthly_log_service
        if output_dir is None and os.environ.get("VERCEL"):
            output_dir = Path(tempfile.gettempdir()) / "precisehub-reports"
        self.output_dir = Path(output_dir or "data/runtime/reports")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def current_month_pdf(self) -> tuple[bytes, str]:
        now = datetime.now()
        return self.month_pdf(now.year, now.month)

    def month_pdf(self, year: int, month: int) -> tuple[bytes, str]:
        month_name = calendar.month_name[month]
        rows = self.monthly_log_service.get_month(year, month)["transactions"]
        title = f"Monthly Report - {month_name} {year}"
        filename = f"precisehub-monthly-report-{year}-{month:02d}.pdf"
        return self._build_pdf(title=title, rows=rows, filename=filename)

    def year_to_date_pdf(self, year: int | None = None) -> tuple[bytes, str]:
        target_year = year or datetime.now().year
        rows = [
            row for row in self.monthly_log_service.get_all_transactions()
            if datetime.fromisoformat(row["paid_at"]).year == target_year
        ]
        title = f"PreciseHub Year To Date Report - {target_year}"
        filename = f"precisehub-ytd-report-{target_year}.pdf"
        return self._build_pdf(title=title, rows=rows, filename=filename)

    def write_current_month_report(self) -> Path:
        pdf_bytes, filename = self.current_month_pdf()
        path = self.output_dir / filename
        path.write_bytes(pdf_bytes)
        return path

    def _build_pdf(self, *, title: str, rows: list[dict], filename: str) -> tuple[bytes, str]:
        buffer = BytesIO()
        document = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            rightMargin=8 * mm,
            leftMargin=8 * mm,
            topMargin=8 * mm,
            bottomMargin=10 * mm,
            title=title,
        )
        styles = getSampleStyleSheet()
        styles["Title"].fontSize = 17
        styles["Title"].leading = 20
        styles["Heading2"].fontSize = 11
        styles["Heading2"].leading = 13
        styles["Heading2"].spaceAfter = 3
        styles.add(ParagraphStyle(name="Muted", parent=styles["Normal"], textColor=colors.HexColor("#5f6d64")))
        styles.add(ParagraphStyle(name="Small", parent=styles["Normal"], fontSize=7, leading=9))

        story = [
            self._logo_header(title, styles),
            Paragraph(f"Generated at {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles["Muted"]),
            Spacer(1, 4 * mm),
        ]

        story.extend(self._summary_section(rows, styles))
        story.extend(self._card_section(rows, styles))
        story.extend(self._transactions_section(rows, styles))

        document.build(story, onFirstPage=self._footer, onLaterPages=self._footer)
        return buffer.getvalue(), filename

    def _summary_section(self, rows: list[dict], styles: dict) -> list:
        totals = self._totals(rows)
        data = [
            ["Transactions", "Total paid", "Reward points", "Bonus points", "Point value", "Net cost"],
            [
                str(totals["count"]),
                self._money(totals["paid"]),
                self._number(totals["points"]),
                self._number(totals["bonus"]),
                self._money(totals["point_value"]),
                self._money(totals["net_cost"]),
            ],
        ]
        return [
            Paragraph("Summary", styles["Heading2"]),
            self._table(data, widths=[32, 36, 36, 36, 36, 36]),
            Spacer(1, 3 * mm),
        ]

    def _card_section(self, rows: list[dict], styles: dict) -> list:
        grouped: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            grouped[row["card_id"]].append(row)

        data = [["Card", "Transactions", "Total paid", "Reward points", "Bonus points", "Net cost"]]
        for card_id, card_rows in sorted(grouped.items()):
            totals = self._totals(card_rows)
            data.append([
                self._card_name(card_id),
                str(totals["count"]),
                self._money(totals["paid"]),
                self._number(totals["points"]),
                self._number(totals["bonus"]),
                self._money(totals["net_cost"]),
            ])
        if len(data) == 1:
            data.append(["No transactions", "0", "Rs 0", "0", "0", "Rs 0"])

        return [
            Paragraph("Card Wise Split", styles["Heading2"]),
            self._table(data, widths=[48, 30, 38, 38, 38, 38], font_size=7),
            Spacer(1, 3 * mm),
        ]

    def _transactions_section(self, rows: list[dict], styles: dict) -> list:
        story = [Paragraph("Detailed Transactions", styles["Heading2"])]
        if not rows:
            story.append(Paragraph("No transactions were logged for this period.", styles["Normal"]))
            return story

        data = [[
            "#", "Date", "Employee", "Booking for", "Type", "Card", "Details",
            "Paid", "Points", "Description",
        ]]
        for index, row in enumerate(sorted(rows, key=lambda item: item["paid_at"]), start=1):
            details = row.get("details") or {}
            vendor_details = [
                self._vendor_name(details.get("vendor_name") or row["vendor_id"]),
                self._route_or_stay(row),
                details.get("airline") or details.get("hotel_name") or "",
                self._class_or_time(row),
                self._flight_notes(row),
            ]
            data.append([
                str(index),
                datetime.fromisoformat(row["paid_at"]).strftime("%Y-%m-%d"),
                details.get("employee_name") or row.get("employee_id") or "",
                details.get("booking_for", ""),
                row["travel_type"].title(),
                self._card_name(row["card_id"]),
                " | ".join(value for value in vendor_details if value),
                self._money(row["final_amount_paid"]),
                self._number(row["total_points"]),
                details.get("description", ""),
            ])
        story.append(self._table(data, widths=[8, 18, 26, 26, 16, 27, 68, 20, 18, 38], font_size=6))
        return story

    def _totals(self, rows: Iterable[dict]) -> dict:
        row_list = list(rows)
        return {
            "count": len(row_list),
            "paid": sum(float(row["final_amount_paid"]) for row in row_list),
            "points": sum(float(row["total_points"]) for row in row_list),
            "bonus": sum(float(row["bonus_points"]) for row in row_list),
            "point_value": sum(float(row["points_value_rupees"]) for row in row_list),
            "net_cost": sum(float(row["net_cost"]) for row in row_list),
        }

    def _table(self, data: list[list[str]], widths: list[int], font_size: int = 8) -> Table:
        cell_style = ParagraphStyle(
            name=f"ReportCell{font_size}",
            fontName="Helvetica",
            fontSize=font_size,
            leading=font_size + 2,
            wordWrap="CJK",
        )
        header_style = ParagraphStyle(
            name=f"ReportHeader{font_size}",
            parent=cell_style,
            fontName="Helvetica-Bold",
            textColor=colors.white,
        )
        wrapped_data = [
            [
                Paragraph(html.escape(str(cell)), header_style if row_index == 0 else cell_style)
                for cell in row
            ]
            for row_index, row in enumerate(data)
        ]
        table = Table(wrapped_data, colWidths=[width * mm for width in widths], repeatRows=1)
        table.hAlign = "LEFT"
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0a4d3f")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), font_size),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#dce4dc")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f7f3")]),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        return table

    def _route_or_stay(self, row: dict) -> str:
        details = row.get("details") or {}
        if row["travel_type"] == "flight":
            return f"{details.get('from', '')} to {details.get('to', '')}".strip()
        if row["travel_type"] == "hotel":
            check_in = " ".join(value for value in [
                details.get("check_in", ""),
                details.get("check_in_time", ""),
            ] if value)
            check_out = " ".join(value for value in [
                details.get("check_out", ""),
                details.get("check_out_time", ""),
            ] if value)
            stay = f"{check_in} to {check_out}".strip()
            return " | ".join(value for value in [details.get("city", ""), stay] if value)
        return details.get("vendor_name", "")

    def _logo_header(self, title: str, styles: dict) -> Table:
        asset_dir = Path(__file__).resolve().parents[1] / "static" / "assets"
        precisehub_logo = self._scaled_image(asset_dir / "precisehub-logo.png", 42 * mm, 13 * mm)
        company_logo = self._scaled_image(asset_dir / "precise-logo-transparent.png", 38 * mm, 17 * mm)
        title_block = [
            Paragraph(title, styles["Title"]),
        ]
        table = Table(
            [[precisehub_logo, title_block, company_logo]],
            colWidths=[62 * mm, 145 * mm, 62 * mm],
        )
        table.hAlign = "LEFT"
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (0, 0), "LEFT"),
            ("ALIGN", (1, 0), (1, 0), "CENTER"),
            ("ALIGN", (2, 0), (2, 0), "RIGHT"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LINEBELOW", (0, 0), (-1, -1), 1.25, colors.HexColor("#0a4d3f")),
        ]))
        return table

    def _scaled_image(self, path: Path, max_width: float, max_height: float) -> Image:
        width, height = ImageReader(str(path)).getSize()
        scale = min(max_width / width, max_height / height)
        return Image(str(path), width=width * scale, height=height * scale)

    def _class_or_time(self, row: dict) -> str:
        details = row.get("details") or {}
        if row["travel_type"] == "flight":
            values = [
                details.get("flight_class", ""),
                f"Outbound: {details.get('outbound_departure_time') or details.get('flight_time')}" if details.get("outbound_departure_time") or details.get("flight_time") else "",
                f"Return: {details.get('return_departure_time') or details.get('return_flight_time')}" if details.get("return_departure_time") or details.get("return_flight_time") else "",
            ]
            return " / ".join(value for value in values if value)
        return ""

    def _flight_notes(self, row: dict) -> str:
        if row["travel_type"] != "flight":
            return ""
        details = row.get("details") or {}
        values = [
            details.get("trip_region", ""),
            details.get("trip_type", ""),
            self._flight_leg_summary(details, "outbound"),
            self._flight_leg_summary(details, "return"),
        ]
        return " | ".join(value for value in values if value)

    def _flight_leg_summary(self, details: dict, prefix: str) -> str:
        is_return = prefix == "return"
        title = "Inbound flight" if is_return else "Outbound flight"
        departure = details.get(f"{prefix}_departure_time") or (
            details.get("return_flight_time") if is_return else details.get("flight_time")
        )
        arrival = details.get(f"{prefix}_arrival_time", "")
        flight_1 = details.get(f"{prefix}_flight_1_duration") or (
            "" if is_return else details.get("flight_duration")
        )
        layover = details.get(f"{prefix}_layover") or (
            "No" if is_return else details.get("layover", "No")
        )
        layover_duration = details.get(f"{prefix}_layover_duration") or (
            "" if is_return else details.get("layover_duration", "")
        )
        connecting_time = details.get(f"{prefix}_connection_time", "")
        flight_2 = details.get(f"{prefix}_flight_2_duration", "")
        cabin_class = details.get(f"{prefix}_cabin_class") or (
            "" if is_return else details.get("flight_class", "")
        )
        parts = [
            f"Departure: {departure}" if departure else "",
            f"Arrival: {arrival}" if arrival else "",
            f"Flight 1: {flight_1}" if flight_1 else "",
            f"Layover: {layover_duration or 'Yes'}" if layover == "Yes" else "Layover: No",
            f"Connecting flight: {connecting_time}" if connecting_time else "",
            f"Flight 2: {flight_2}" if flight_2 else "",
            f"Cabin class: {cabin_class}" if cabin_class else "",
        ]
        summary = "; ".join(value for value in parts if value)
        return f"{title}: {summary}" if summary else ""

    def _money(self, value: float | str) -> str:
        return f"Rs {float(value):,.0f}"

    def _number(self, value: float | str) -> str:
        return f"{float(value):,.0f}"

    def _vendor_name(self, vendor_id: str) -> str:
        if "_" not in vendor_id:
            return vendor_id
        names = {
            "amex_fine_hotels": "American Express Fine Hotels",
            "amex_mmt_flight_voucher": "American Express MMT Flight Voucher",
            "amex_cleartrip_generic_voucher": "American Express Cleartrip Voucher",
            "amex_goibibo_hotel_voucher": "American Express Goibibo Hotel Voucher",
            "amex_easemytrip_hotel_voucher": "American Express EaseMyTrip Hotel Voucher",
            "amex_mmt_hotel_voucher": "American Express MMT Hotel Voucher",
            "amex_cleartrip_hotel_voucher": "American Express Cleartrip Hotel Voucher",
            "hdfc_smartbuy_flight": "HDFC SmartBuy Flight",
            "hdfc_smartbuy_hotel": "HDFC SmartBuy Hotel",
            "icici_ishop_flight": "ICICI iShop Flight",
            "icici_ishop_hotel": "ICICI iShop Hotel",
            "travel_agent_flight": "Travel Agent",
            "travel_agent_hotel": "Travel Agent",
        }
        if vendor_id in names:
            return names[vendor_id]
        acronyms = {"amex": "American Express", "hdfc": "HDFC", "icici": "ICICI", "mmt": "MMT"}
        return " ".join(acronyms.get(part, part.title()) for part in vendor_id.split("_"))

    def _card_name(self, card_id: str) -> str:
        names = {
            "amex": "American Express",
            "hdfc_infinia": "HDFC Infinia",
            "icici_times_black": "ICICI Times Black",
            "bank_transfer": "Bank Transfer",
        }
        return names.get(card_id, card_id)

    def _footer(self, canvas, document) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#5f6d64"))
        canvas.drawString(12 * mm, 8 * mm, "PreciseHub")
        canvas.drawRightString(285 * mm, 8 * mm, f"Page {document.page}")
        canvas.restoreState()
